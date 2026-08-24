"""Construct rendering inputs that cannot retain hidden state."""

from __future__ import annotations

from collections import defaultdict

from diplomacy_app.domain.models import (
    BuildOrder,
    CanonicalOrder,
    ConvoyOrder,
    DisbandOrder,
    EffectiveOrder,
    HiddenTerritory,
    HoldOrder,
    LabelMode,
    MapDefinition,
    MoveOrder,
    OrderResult,
    PerspectiveKind,
    PhaseSnapshot,
    ProjectedMapState,
    ProjectedOrder,
    ProjectedTerritory,
    ProjectionRequest,
    RetreatOrder,
    SupportOrder,
    TerritoryId,
    VisibilityPolicy,
    VisibleTerritory,
    WaiveOrder,
)


def _locations(order: CanonicalOrder) -> frozenset[TerritoryId]:
    if isinstance(order, WaiveOrder):
        return frozenset()
    values = {order.unit.location.territory_id}
    if isinstance(order, (MoveOrder, RetreatOrder)):
        values.add(order.destination.territory_id)
    elif isinstance(order, SupportOrder):
        values.add(order.supported_unit.location.territory_id)
        if order.destination:
            values.add(order.destination.territory_id)
    elif isinstance(order, ConvoyOrder):
        values.add(order.convoyed_army.location.territory_id)
        values.add(order.destination.territory_id)
    elif isinstance(order, (HoldOrder, BuildOrder, DisbandOrder)):
        pass
    return frozenset(values)


class VisibilityProjector:
    def _visible(
        self,
        map_definition: MapDefinition,
        phase: PhaseSnapshot,
        policy: VisibilityPolicy,
        request: ProjectionRequest,
    ) -> set[TerritoryId]:
        all_territories = {item.id for item in map_definition.territories}
        if request.perspective.kind is PerspectiveKind.GAMEMASTER or not policy.enabled:
            return all_territories
        power_id = request.perspective.power_id
        visible = {
            unit.location.territory_id for unit in phase.state.units if unit.power_id == power_id
        }
        visible.update(
            unit.unit.location.territory_id
            for unit in phase.state.dislodged_units
            if unit.unit.power_id == power_id
        )
        graph: dict[TerritoryId, set[TerritoryId]] = defaultdict(set)
        for edge in map_definition.adjacencies:
            graph[edge.origin.territory_id].add(edge.destination.territory_id)
        frontier = set(visible)
        for _ in range(policy.adjacency_depth):
            frontier = {
                destination for origin in frontier for destination in graph[origin]
            } - visible
            visible.update(frontier)
        return visible

    def project(
        self,
        map_definition: MapDefinition,
        phase: PhaseSnapshot,
        effective_orders: tuple[EffectiveOrder, ...],
        policy: VisibilityPolicy,
        request: ProjectionRequest,
    ) -> ProjectedMapState:
        visible_ids = self._visible(map_definition, phase, policy, request)
        units = {item.location.territory_id: item for item in phase.state.units}
        dislodged = {
            item.unit.location.territory_id: item.unit for item in phase.state.dislodged_units
        }
        territories: list[ProjectedTerritory] = []
        for definition in map_definition.territories:
            label = (
                definition.display_name
                if request.label_mode is LabelMode.FULL_NAME
                else definition.abbreviation
            )
            if definition.id not in visible_ids:
                territories.append(HiddenTerritory(definition.id, label))
            else:
                territories.append(
                    VisibleTerritory(
                        definition.id,
                        label,
                        phase.state.territory_controllers.get(definition.id),
                        phase.state.supply_centre_owners.get(definition.id),
                        units.get(definition.id),
                        dislodged.get(definition.id),
                    )
                )
        retained = tuple(
            ProjectedOrder(item.source_line, item.order, item.is_valid)
            for item in effective_orders
            if request.include_orders and _locations(item.order) <= visible_ids
        )
        retained_lines = {item.source_line for item in retained}
        results: tuple[OrderResult, ...] = ()
        if request.include_results:
            results = tuple(
                item
                for item in phase.results
                if item.source_line in retained_lines and _locations(item.order) <= visible_ids
            )
        return ProjectedMapState(
            phase.phase_id,
            request.perspective,
            tuple(territories),
            retained,
            results,
        )
