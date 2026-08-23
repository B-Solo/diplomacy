"""Standard Diplomacy rules backed by the pinned ``diplomacy`` package."""

from __future__ import annotations

from collections import defaultdict, deque

from diplomacy_app.domain.errors import RulesEngineError
from diplomacy_app.domain.models import (
    AdjudicationProposal,
    BuildOrder,
    CanonicalOrder,
    DisbandOrder,
    EffectiveOrder,
    GameState,
    HoldOrder,
    Issue,
    IssueSeverity,
    Location,
    MapDefinition,
    OrderCandidate,
    OrderResult,
    PhaseId,
    PhaseRequirements,
    PhaseSnapshot,
    PowerId,
    PowerPhaseRequirement,
    RuleValidation,
    Season,
    UnitPosition,
    UnitRef,
    UnitType,
    WaiveOrder,
)
from diplomacy_app.rules_engine.map_adapter import (
    abbreviation_indexes,
    engine_power,
)
from diplomacy_app.rules_engine.order_adapter import to_engine_order
from diplomacy_app.rules_engine.state_adapter import (
    make_game,
    phase_from_engine,
    state_from_game,
)


def _ref(value: UnitPosition) -> UnitRef:
    return UnitRef(value.power_id, value.unit_type, value.location)


def _unit_key(order: object) -> tuple[PowerId, object] | None:
    unit = getattr(order, "unit", None)
    return (unit.power_id, unit.location) if unit else None


class StandardRulesEngine:
    """Deterministic adapter around the vendored adjudicator."""

    engine_id = "standard"

    def describe_phase(
        self, map_definition: MapDefinition, phase_id: PhaseId, state: GameState
    ) -> PhaseRequirements:
        requirements: dict[PowerId, PowerPhaseRequirement] = {}
        for power in map_definition.powers:
            if phase_id.season in {Season.SPRING, Season.FALL}:
                units = tuple(_ref(unit) for unit in state.units if unit.power_id == power.id)
                requirements[power.id] = PowerPhaseRequirement(power.id, units)
            elif phase_id.season in {Season.SUMMER, Season.WINTER}:
                units = tuple(
                    _ref(unit.unit)
                    for unit in state.dislodged_units
                    if unit.unit.power_id == power.id
                )
                requirements[power.id] = PowerPhaseRequirement(power.id, units)
            else:
                unit_count = sum(unit.power_id == power.id for unit in state.units)
                centre_count = sum(
                    owner == power.id for owner in state.supply_centre_owners.values()
                )
                difference = centre_count - unit_count
                requirements[power.id] = PowerPhaseRequirement(
                    power.id,
                    (),
                    build_count=max(0, difference),
                    disband_count=max(0, -difference),
                )
        return PhaseRequirements(phase_id, requirements)

    def _invalid_default(
        self, phase_id: PhaseId, power_id: PowerId, candidate: OrderCandidate
    ) -> CanonicalOrder | None:
        unit = getattr(candidate.order, "unit", None)
        if phase_id.season in {Season.SPRING, Season.FALL} and unit:
            return HoldOrder(unit)
        if phase_id.season in {Season.SUMMER, Season.WINTER} and unit:
            return DisbandOrder(unit)
        if phase_id.season is Season.YEAR_END:
            return WaiveOrder(power_id)
        return None

    def validate(
        self,
        map_definition: MapDefinition,
        phase_id: PhaseId,
        state: GameState,
        power_id: PowerId,
        candidates: tuple[OrderCandidate, ...],
    ) -> tuple[RuleValidation, ...]:
        game = make_game(map_definition, phase_id, state)
        recognised = [candidate for candidate in candidates if candidate.order is not None]
        grouped: dict[tuple[PowerId, object], list[int]] = defaultdict(list)
        for candidate in recognised:
            assert candidate.order is not None
            key = _unit_key(candidate.order)
            if key:
                grouped[key].append(candidate.source.number)
        duplicates = {line for lines in grouped.values() if len(lines) > 1 for line in lines}
        results: list[RuleValidation] = []
        for candidate in recognised:
            assert candidate.order is not None
            if candidate.source.number in duplicates:
                issue = Issue(
                    "order.duplicate_unit",
                    "Multiple orders were submitted for the same unit",
                    IssueSeverity.ERROR,
                )
                results.append(
                    RuleValidation(
                        candidate.source.number,
                        False,
                        (issue,),
                        self._invalid_default(phase_id, power_id, candidate),
                    )
                )
                continue
            before = len(game.error)
            try:
                game.set_orders(
                    engine_power(power_id),
                    [to_engine_order(map_definition, candidate.order)],
                    replace=False,
                )
                errors = game.error[before:]
            except Exception as exc:
                errors = [str(exc)]
            issues = tuple(
                Issue("order.illegal", str(message), IssueSeverity.ERROR) for message in errors
            )
            valid = not issues
            results.append(
                RuleValidation(
                    candidate.source.number,
                    valid,
                    issues,
                    candidate.order
                    if valid
                    else self._invalid_default(phase_id, power_id, candidate),
                )
            )
        return tuple(results)

    def _automatic_disbands(
        self,
        map_definition: MapDefinition,
        state: GameState,
        power_id: PowerId,
        count: int,
        excluded: set[Location],
    ) -> tuple[DisbandOrder, ...]:
        graph: dict[object, set[object]] = defaultdict(set)
        for edge in map_definition.adjacencies:
            graph[edge.origin.territory_id].add(edge.destination.territory_id)
        homes = next(
            power.home_supply_centres for power in map_definition.powers if power.id == power_id
        )

        def distance(origin: object) -> int:
            queue = deque([(origin, 0)])
            seen = {origin}
            while queue:
                current, steps = queue.popleft()
                if current in homes:
                    return steps
                for destination in graph[current]:
                    if destination not in seen:
                        seen.add(destination)
                        queue.append((destination, steps + 1))
            return 10_000

        choices = [
            unit
            for unit in state.units
            if unit.power_id == power_id and unit.location not in excluded
        ]
        choices.sort(
            key=lambda unit: (
                -distance(unit.location.territory_id),
                0 if unit.unit_type is UnitType.FLEET else 1,
                unit.location.territory_id,
            )
        )
        return tuple(DisbandOrder(_ref(unit)) for unit in choices[:count])

    def effective_orders(
        self, map_definition: MapDefinition, phase: PhaseSnapshot
    ) -> tuple[EffectiveOrder, ...]:
        requirements = self.describe_phase(map_definition, phase.phase_id, phase.state)
        effective: list[EffectiveOrder] = []
        ordered_locations: set[tuple[PowerId, object]] = set()
        for power in map_definition.powers:
            submission = phase.submissions.get(power.id)
            if submission:
                for line in submission.lines:
                    candidate = line.candidate
                    validation = line.validation
                    if candidate.order is None or validation is None:
                        continue
                    order = candidate.order if validation.is_valid else validation.effective_order
                    if order is None:
                        continue
                    effective.append(
                        EffectiveOrder(
                            power.id,
                            candidate.source.number,
                            candidate.order,
                            order,
                            validation.is_valid,
                        )
                    )
                    key = _unit_key(order)
                    if key:
                        ordered_locations.add(key)
            requirement = requirements.by_power[power.id]
            if phase.phase_id.season in {Season.SPRING, Season.FALL}:
                for unit in requirement.units_requiring_orders:
                    if (power.id, unit.location) not in ordered_locations:
                        effective.append(
                            EffectiveOrder(power.id, None, None, HoldOrder(unit), None)
                        )
            elif phase.phase_id.season in {Season.SUMMER, Season.WINTER}:
                for unit in requirement.units_requiring_orders:
                    if (power.id, unit.location) not in ordered_locations:
                        effective.append(
                            EffectiveOrder(power.id, None, None, DisbandOrder(unit), None)
                        )
            elif requirement.build_count:
                represented = sum(
                    item.power_id == power.id and isinstance(item.order, (BuildOrder, WaiveOrder))
                    for item in effective
                )
                for _ in range(max(0, requirement.build_count - represented)):
                    effective.append(
                        EffectiveOrder(power.id, None, None, WaiveOrder(power.id), None)
                    )
            elif requirement.disband_count:
                submitted = {
                    item.order.unit.location
                    for item in effective
                    if item.power_id == power.id and isinstance(item.order, DisbandOrder)
                }
                missing = max(0, requirement.disband_count - len(submitted))
                for order in self._automatic_disbands(
                    map_definition, phase.state, power.id, missing, submitted
                ):
                    effective.append(EffectiveOrder(power.id, None, None, order, None))
        return tuple(effective)

    def adjudicate(
        self, map_definition: MapDefinition, phase: PhaseSnapshot
    ) -> AdjudicationProposal:
        game = make_game(map_definition, phase.phase_id, phase.state)
        game.add_rule("NO_CHECK")
        effective = self.effective_orders(map_definition, phase)
        try:
            for power in map_definition.powers:
                submission = phase.submissions.get(power.id)
                raw_orders = []
                if submission:
                    raw_orders = [
                        to_engine_order(map_definition, line.candidate.order)
                        for line in submission.lines
                        if line.candidate.order is not None
                    ]
                game.set_orders(engine_power(power.id), raw_orders, replace=False)
            processed = game.process()
            engine_results = processed.results
            _, reverse_names = abbreviation_indexes(map_definition)
            results: list[OrderResult] = []
            for item in effective:
                unit = getattr(item.order, "unit", None)
                key = None
                if unit:
                    prefix = "A" if unit.unit_type is UnitType.ARMY else "F"
                    key = f"{prefix} {reverse_names[unit.location]}"
                outcomes = engine_results.get(key, []) if key else []
                codes = tuple(
                    str(outcome).strip().upper().replace(" ", "_") or "OK" for outcome in outcomes
                )
                if item.is_valid is False and "VOID" not in codes:
                    codes = (*codes, "VOID")
                results.append(OrderResult(item.power_id, item.source_line, item.order, codes))
            return AdjudicationProposal(
                phase.phase_id,
                phase_from_engine(game.current_short_phase),
                state_from_game(map_definition, game),
                tuple(results),
            )
        except RulesEngineError:
            raise
        except Exception as exc:
            raise RulesEngineError(f"Adjudication failed: {exc}") from exc
