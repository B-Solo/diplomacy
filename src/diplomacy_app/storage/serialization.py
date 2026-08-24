"""Explicit JSON codecs for application-owned immutable values."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from diplomacy_app.domain.errors import InvalidStoredData
from diplomacy_app.domain.models import (
    Adjacency,
    BuildOrder,
    CanonicalOrder,
    CoastId,
    ConvoyOrder,
    DisbandOrder,
    DislodgedUnit,
    GameState,
    HoldOrder,
    Issue,
    IssueSeverity,
    Location,
    MapAssets,
    MapDefinition,
    MapId,
    MapPresentation,
    MoveOrder,
    OrderCandidate,
    OrderResult,
    OrderSubmission,
    PhaseId,
    Point,
    PowerDefinition,
    PowerId,
    RetreatOrder,
    RuleValidation,
    Season,
    SourceLine,
    StartingSetup,
    SubmissionLine,
    SupportOrder,
    TerritoryDefinition,
    TerritoryId,
    TerritoryKind,
    UnitPosition,
    UnitRef,
    UnitType,
    WaiveOrder,
)
from diplomacy_app.presentation import (
    DEFAULT_COAST_LABEL_FONT_SIZE,
    DEFAULT_TERRITORY_LABEL_FONT_SIZE,
    default_coast_label_anchor,
)


def location_data(value: Location) -> dict[str, str | None]:
    return {"territory": value.territory_id, "coast": value.coast_id}


def location_from_data(value: Any) -> Location:
    if not isinstance(value, dict):
        raise InvalidStoredData("Location must be an object")
    coast = value.get("coast")
    return Location(TerritoryId(str(value["territory"])), CoastId(str(coast)) if coast else None)


def unit_ref_data(value: UnitRef) -> dict[str, Any]:
    return {
        "power": value.power_id,
        "type": value.unit_type.value,
        "location": location_data(value.location),
    }


def unit_ref_from_data(value: Any) -> UnitRef:
    if not isinstance(value, dict):
        raise InvalidStoredData("Unit reference must be an object")
    return UnitRef(
        PowerId(str(value["power"])),
        UnitType(str(value["type"])),
        location_from_data(value["location"]),
    )


def order_data(value: CanonicalOrder) -> dict[str, Any]:
    if isinstance(value, HoldOrder):
        return {"kind": "hold", "unit": unit_ref_data(value.unit)}
    if isinstance(value, MoveOrder):
        return {
            "kind": "move",
            "unit": unit_ref_data(value.unit),
            "destination": location_data(value.destination),
            "via_convoy": value.via_convoy,
        }
    if isinstance(value, SupportOrder):
        return {
            "kind": "support",
            "unit": unit_ref_data(value.unit),
            "supported_unit": unit_ref_data(value.supported_unit),
            "destination": location_data(value.destination) if value.destination else None,
        }
    if isinstance(value, ConvoyOrder):
        return {
            "kind": "convoy",
            "unit": unit_ref_data(value.unit),
            "convoyed_army": unit_ref_data(value.convoyed_army),
            "destination": location_data(value.destination),
        }
    if isinstance(value, RetreatOrder):
        return {
            "kind": "retreat",
            "unit": unit_ref_data(value.unit),
            "destination": location_data(value.destination),
        }
    if isinstance(value, BuildOrder):
        return {"kind": "build", "unit": unit_ref_data(value.unit)}
    if isinstance(value, DisbandOrder):
        return {"kind": "disband", "unit": unit_ref_data(value.unit)}
    if isinstance(value, WaiveOrder):
        return {"kind": "waive", "power": value.power_id}
    raise TypeError(f"Unsupported order value: {type(value).__name__}")


def order_from_data(value: Any) -> CanonicalOrder:
    if not isinstance(value, dict):
        raise InvalidStoredData("Order must be an object")
    kind = value.get("kind")
    if kind == "hold":
        return HoldOrder(unit_ref_from_data(value["unit"]))
    if kind == "move":
        return MoveOrder(
            unit_ref_from_data(value["unit"]),
            location_from_data(value["destination"]),
            bool(value.get("via_convoy", False)),
        )
    if kind == "support":
        destination = value.get("destination")
        return SupportOrder(
            unit_ref_from_data(value["unit"]),
            unit_ref_from_data(value["supported_unit"]),
            location_from_data(destination) if destination else None,
        )
    if kind == "convoy":
        return ConvoyOrder(
            unit_ref_from_data(value["unit"]),
            unit_ref_from_data(value["convoyed_army"]),
            location_from_data(value["destination"]),
        )
    if kind == "retreat":
        return RetreatOrder(
            unit_ref_from_data(value["unit"]), location_from_data(value["destination"])
        )
    if kind == "build":
        return BuildOrder(unit_ref_from_data(value["unit"]))
    if kind == "disband":
        return DisbandOrder(unit_ref_from_data(value["unit"]))
    if kind == "waive":
        return WaiveOrder(PowerId(str(value["power"])))
    raise InvalidStoredData(f"Unknown order kind: {kind}")


def issue_data(value: Issue) -> dict[str, str]:
    return {"code": value.code, "message": value.message, "severity": value.severity.value}


def issue_from_data(value: Any) -> Issue:
    return Issue(str(value["code"]), str(value["message"]), IssueSeverity(str(value["severity"])))


def submission_data(value: OrderSubmission) -> dict[str, Any]:
    lines: list[dict[str, Any]] = []
    for line in value.lines:
        candidate = line.candidate
        validation = line.validation
        lines.append(
            {
                "source": {"number": candidate.source.number, "text": candidate.source.text},
                "order": order_data(candidate.order) if candidate.order else None,
                "canonical_text": candidate.canonical_text,
                "parser_issues": [issue_data(item) for item in candidate.parser_issues],
                "validation": {
                    "source_line": validation.source_line,
                    "is_valid": validation.is_valid,
                    "issues": [issue_data(item) for item in validation.issues],
                    "effective_order": order_data(validation.effective_order)
                    if validation.effective_order
                    else None,
                }
                if validation
                else None,
            }
        )
    return {
        "power": value.power_id,
        "raw_text": value.raw_text,
        "lines": lines,
        "is_final": value.is_final,
    }


def submission_from_data(value: Any) -> OrderSubmission:
    if not isinstance(value, dict):
        raise InvalidStoredData("Submission must be an object")
    lines: list[SubmissionLine] = []
    for item in value.get("lines", []):
        source = item["source"]
        candidate = OrderCandidate(
            SourceLine(int(source["number"]), str(source["text"])),
            order_from_data(item["order"]) if item.get("order") else None,
            item.get("canonical_text"),
            tuple(issue_from_data(issue) for issue in item.get("parser_issues", [])),
        )
        raw_validation = item.get("validation")
        validation = None
        if raw_validation:
            validation = RuleValidation(
                int(raw_validation["source_line"]),
                bool(raw_validation["is_valid"]),
                tuple(issue_from_data(issue) for issue in raw_validation.get("issues", [])),
                order_from_data(raw_validation["effective_order"])
                if raw_validation.get("effective_order")
                else None,
            )
        lines.append(SubmissionLine(candidate, validation))
    return OrderSubmission(
        PowerId(str(value["power"])),
        str(value.get("raw_text", "")),
        tuple(lines),
        bool(value.get("is_final", False)),
    )


def unit_position_data(value: UnitPosition) -> dict[str, Any]:
    return {
        "power": value.power_id,
        "type": value.unit_type.value,
        "location": location_data(value.location),
    }


def unit_position_from_data(value: Any) -> UnitPosition:
    return UnitPosition(
        PowerId(str(value["power"])),
        UnitType(str(value["type"])),
        location_from_data(value["location"]),
    )


def state_data(value: GameState, phase_id: PhaseId) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": {"year": phase_id.year, "season": phase_id.season.value},
        "units": [unit_position_data(item) for item in value.units],
        "dislodged_units": [
            {
                "unit": unit_position_data(item.unit),
                "retreat_options": [location_data(option) for option in item.retreat_options],
            }
            for item in value.dislodged_units
        ],
        "territory_controllers": {
            str(key): value for key, value in sorted(value.territory_controllers.items())
        },
        "supply_centre_owners": {
            str(key): value for key, value in sorted(value.supply_centre_owners.items())
        },
    }


def state_from_data(value: Any) -> tuple[PhaseId, GameState]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise InvalidStoredData("Unsupported state schema")
    phase_value = value["phase"]
    phase = PhaseId(int(phase_value["year"]), Season(str(phase_value["season"])))
    state = GameState(
        tuple(unit_position_from_data(item) for item in value.get("units", [])),
        tuple(
            DislodgedUnit(
                unit_position_from_data(item["unit"]),
                tuple(location_from_data(option) for option in item.get("retreat_options", [])),
            )
            for item in value.get("dislodged_units", [])
        ),
        MappingProxyType(
            {
                TerritoryId(str(key)): PowerId(str(owner)) if owner else None
                for key, owner in value.get("territory_controllers", {}).items()
            }
        ),
        MappingProxyType(
            {
                TerritoryId(str(key)): PowerId(str(owner)) if owner else None
                for key, owner in value.get("supply_centre_owners", {}).items()
            }
        ),
    )
    return phase, state


def orders_document_data(
    submissions: dict[PowerId, OrderSubmission] | Any, results: tuple[OrderResult, ...]
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "submissions": {
            str(key): submission_data(value) for key, value in sorted(submissions.items())
        },
        "results": [
            {
                "power": item.power_id,
                "source_line": item.source_line,
                "order": order_data(item.order),
                "outcomes": list(item.outcome_codes),
            }
            for item in results
        ],
    }


def orders_document_from_data(
    value: Any,
) -> tuple[dict[PowerId, OrderSubmission], tuple[OrderResult, ...]]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise InvalidStoredData("Unsupported orders schema")
    submissions = {
        PowerId(str(key)): submission_from_data(item)
        for key, item in value.get("submissions", {}).items()
    }
    results = tuple(
        OrderResult(
            PowerId(str(item["power"])),
            item.get("source_line"),
            order_from_data(item["order"]),
            tuple(str(code) for code in item.get("outcomes", [])),
        )
        for item in value.get("results", [])
    )
    return submissions, results


def map_definition_data(value: MapDefinition) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "map_id": value.id,
        "name": value.name,
        "rules_engine": value.rules_engine_id,
        "territories": [
            {
                "id": item.id,
                "name": item.name,
                "display_name": item.display_name,
                "abbreviation": item.abbreviation,
                "kind": item.kind.value,
                "svg_element": item.svg_element_id,
                "split_coasts": list(item.split_coast_ids),
                "supply_centre": item.is_supply_centre,
            }
            for item in value.territories
        ],
        "adjacencies": [
            {
                "origin": location_data(item.origin),
                "destination": location_data(item.destination),
                "unit": item.unit_type.value,
            }
            for item in sorted(
                value.adjacencies,
                key=lambda edge: (
                    edge.origin.territory_id,
                    edge.origin.coast_id or "",
                    edge.destination.territory_id,
                    edge.destination.coast_id or "",
                    edge.unit_type.value,
                ),
            )
        ],
        "powers": [
            {
                "id": item.id,
                "name": item.name,
                "colour": item.colour,
                "home_supply_centres": sorted(item.home_supply_centres),
            }
            for item in value.powers
        ],
        "start": state_data(
            value.default_starting_setup.state, value.default_starting_setup.phase_id
        ),
        "presentation": {
            "territory_label_font_size": value.presentation.territory_label_font_size,
            "coast_label_font_size": value.presentation.coast_label_font_size,
            "labels": {
                str(key): [point.x, point.y]
                for key, point in value.presentation.label_anchors.items()
            },
            "abbreviations": {
                str(key): [point.x, point.y]
                for key, point in value.presentation.abbreviation_anchors.items()
            },
            "armies": {
                str(key): [point.x, point.y]
                for key, point in value.presentation.army_anchors.items()
            },
            "fleets": [
                {"location": location_data(key), "point": [point.x, point.y]}
                for key, point in value.presentation.fleet_anchors.items()
            ],
            "coast_labels": [
                {
                    "location": location_data(key),
                    "point": [point.x, point.y],
                    "rotation": value.presentation.coast_label_rotations.get(key, 0),
                }
                for key, point in value.presentation.coast_label_anchors.items()
            ],
            "supply_centres": {
                str(key): [point.x, point.y]
                for key, point in value.presentation.supply_centre_anchors.items()
            },
        },
    }


def map_definition_from_data(value: Any, assets: MapAssets) -> MapDefinition:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise InvalidStoredData("Unsupported compiled-map schema")
    phase, state = state_from_data(value["start"])
    presentation = value["presentation"]

    def point(item: Any) -> Point:
        return Point(float(item[0]), float(item[1]))

    label_anchors = {
        TerritoryId(str(key)): point(item) for key, item in presentation.get("labels", {}).items()
    }
    abbreviation_anchors = {
        TerritoryId(str(key)): point(item)
        for key, item in presentation.get("abbreviations", {}).items()
    }
    if not abbreviation_anchors:
        abbreviation_anchors = dict(label_anchors)
    fleet_anchors = {
        location_from_data(item["location"]): point(item["point"])
        for item in presentation.get("fleets", [])
    }
    coast_label_items = presentation.get("coast_labels", [])
    coast_label_anchors = {
        location_from_data(item["location"]): point(item["point"]) for item in coast_label_items
    }
    coast_label_rotations = {
        location_from_data(item["location"]): float(item.get("rotation", 0))
        for item in coast_label_items
    }
    for location, fleet_anchor in fleet_anchors.items():
        if location.coast_id is not None and location not in coast_label_anchors:
            coast_label_anchors[location] = default_coast_label_anchor(
                location.coast_id, fleet_anchor
            )
            coast_label_rotations[location] = 0

    return MapDefinition(
        MapId(str(value["map_id"])),
        str(value["name"]),
        tuple(
            TerritoryDefinition(
                TerritoryId(str(item["id"])),
                str(item["name"]),
                str(item.get("display_name", item["name"])),
                str(item["abbreviation"]),
                TerritoryKind(str(item["kind"])),
                str(item["svg_element"]),
                tuple(CoastId(str(coast)) for coast in item.get("split_coasts", [])),
                bool(item.get("supply_centre", False)),
            )
            for item in value["territories"]
        ),
        frozenset(
            Adjacency(
                location_from_data(item["origin"]),
                location_from_data(item["destination"]),
                UnitType(str(item["unit"])),
            )
            for item in value["adjacencies"]
        ),
        tuple(
            PowerDefinition(
                PowerId(str(item["id"])),
                str(item["name"]),
                str(item["colour"]),
                frozenset(TerritoryId(str(sc)) for sc in item.get("home_supply_centres", [])),
            )
            for item in value["powers"]
        ),
        StartingSetup(phase, state),
        MapPresentation(
            MappingProxyType(label_anchors),
            MappingProxyType(abbreviation_anchors),
            MappingProxyType(
                {
                    TerritoryId(str(key)): point(item)
                    for key, item in presentation.get("armies", {}).items()
                }
            ),
            MappingProxyType(fleet_anchors),
            MappingProxyType(coast_label_anchors),
            MappingProxyType(coast_label_rotations),
            MappingProxyType(
                {
                    TerritoryId(str(key)): point(item)
                    for key, item in presentation.get("supply_centres", {}).items()
                }
            ),
            float(presentation.get("territory_label_font_size", DEFAULT_TERRITORY_LABEL_FONT_SIZE)),
            float(presentation.get("coast_label_font_size", DEFAULT_COAST_LABEL_FONT_SIZE)),
        ),
        assets,
        str(value.get("rules_engine", "standard")),
    )
