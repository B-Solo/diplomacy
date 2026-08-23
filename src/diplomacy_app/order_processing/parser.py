"""Line-oriented, source-preserving Diplomacy order parser."""

from __future__ import annotations

import re

from diplomacy_app.domain.models import (
    BuildOrder,
    CanonicalOrder,
    ConvoyOrder,
    DisbandOrder,
    HoldOrder,
    Issue,
    IssueSeverity,
    Location,
    MapDefinition,
    MoveOrder,
    OrderCandidate,
    PowerId,
    RetreatOrder,
    SourceLine,
    SupportOrder,
    UnitRef,
    UnitType,
    WaiveOrder,
)


class _ParseFailure(ValueError):
    pass


def _indexes(map_definition: MapDefinition) -> tuple[dict[str, Location], dict[Location, str]]:
    names: dict[str, Location] = {}
    display: dict[Location, str] = {}
    for territory in map_definition.territories:
        base = Location(territory.id)
        names[territory.name.casefold()] = base
        names[territory.abbreviation.casefold()] = base
        display[base] = territory.abbreviation
        for coast in territory.split_coast_ids:
            location = Location(territory.id, coast)
            for separator in ("/", " "):
                names[f"{territory.name}{separator}{coast}".casefold()] = location
                names[f"{territory.abbreviation}{separator}{coast}".casefold()] = location
            display[location] = f"{territory.abbreviation}/{str(coast).upper()}"
    return names, display


def _normalise_locations(
    text: str, names: dict[str, Location], display: dict[Location, str]
) -> str:
    result = text
    for name, location in sorted(names.items(), key=lambda item: len(item[0]), reverse=True):
        if " " not in name and "/" not in name:
            continue
        result = re.sub(
            rf"(?<![\w]){re.escape(name)}(?![\w])",
            display[location],
            result,
            flags=re.IGNORECASE,
        )
    return result


def _location(token: str, names: dict[str, Location]) -> Location:
    normal = token.strip(".,;:()[]").casefold()
    if normal not in names:
        raise _ParseFailure(f"Unknown or ambiguous territory: {token}")
    return names[normal]


def _unit_type(token: str) -> UnitType:
    value = token.strip(".,;:()[]").casefold()
    if value in {"a", "army"}:
        return UnitType.ARMY
    if value in {"f", "fleet"}:
        return UnitType.FLEET
    raise _ParseFailure(f"Expected A/Army or F/Fleet, found: {token}")


def _unit(
    tokens: list[str], start: int, power_id: PowerId, names: dict[str, Location]
) -> tuple[UnitRef, int]:
    if len(tokens) <= start + 1:
        raise _ParseFailure("An order must identify a unit type and territory")
    return UnitRef(
        power_id, _unit_type(tokens[start]), _location(tokens[start + 1], names)
    ), start + 2


def canonical_text(order: object, map_definition: MapDefinition) -> str:
    _, display = _indexes(map_definition)

    def unit(value: UnitRef) -> str:
        prefix = "A" if value.unit_type is UnitType.ARMY else "F"
        return f"{prefix} {display[value.location]}"

    if isinstance(order, WaiveOrder):
        return "Waive"
    if isinstance(order, HoldOrder):
        return f"{unit(order.unit)} H"
    if isinstance(order, MoveOrder):
        return f"{unit(order.unit)} - {display[order.destination]}" + (
            " via convoy" if order.via_convoy else ""
        )
    if isinstance(order, SupportOrder):
        destination = f" - {display[order.destination]}" if order.destination else ""
        return f"{unit(order.unit)} S {unit(order.supported_unit)}{destination}"
    if isinstance(order, ConvoyOrder):
        return f"{unit(order.unit)} C {unit(order.convoyed_army)} - {display[order.destination]}"
    if isinstance(order, RetreatOrder):
        return f"{unit(order.unit)} R {display[order.destination]}"
    if isinstance(order, BuildOrder):
        return f"{unit(order.unit)} B"
    if isinstance(order, DisbandOrder):
        return f"{unit(order.unit)} D"
    raise TypeError(type(order).__name__)


def parse_line(
    map_definition: MapDefinition, power_id: PowerId, source: SourceLine
) -> OrderCandidate:
    names, display = _indexes(map_definition)
    text = _normalise_locations(source.text.strip(), names, display)
    text = re.sub(r"(?:->|→|–|—)", " - ", text)
    text = re.sub(r"\b(?:moves?|to)\b", " - ", text, flags=re.IGNORECASE)
    tokens = [value for value in re.split(r"\s+", text) if value]
    order: CanonicalOrder
    try:
        if not tokens:
            raise _ParseFailure("Empty order line")
        first = tokens[0].strip(".,;:").casefold()
        if first in {"waive", "waived"}:
            order = WaiveOrder(power_id)
        else:
            prefix_action = None
            if first in {"build", "disband", "remove"}:
                prefix_action = first
                tokens = tokens[1:]
            unit, position = _unit(tokens, 0, power_id, names)
            if prefix_action:
                order = BuildOrder(unit) if prefix_action == "build" else DisbandOrder(unit)
            else:
                if position >= len(tokens):
                    raise _ParseFailure("The order action is missing")
                action = tokens[position].strip(".,;:").casefold()
                position += 1
                if action in {"h", "hold", "holds"}:
                    order = HoldOrder(unit)
                elif action == "-":
                    if position >= len(tokens):
                        raise _ParseFailure("Move destination is missing")
                    destination = _location(tokens[position], names)
                    via_convoy = any(
                        value.casefold() in {"via", "convoy"} for value in tokens[position + 1 :]
                    )
                    order = MoveOrder(unit, destination, via_convoy)
                elif action in {"s", "support", "supports"}:
                    supported, position = _unit(tokens, position, PowerId(""), names)
                    destination = None
                    if position < len(tokens):
                        if tokens[position] != "-":
                            raise _ParseFailure("Expected '-' before supported move destination")
                        if position + 1 >= len(tokens):
                            raise _ParseFailure("Supported move destination is missing")
                        destination = _location(tokens[position + 1], names)
                    order = SupportOrder(unit, supported, destination)
                elif action in {"c", "convoy", "convoys"}:
                    convoyed, position = _unit(tokens, position, PowerId(""), names)
                    if (
                        position >= len(tokens)
                        or tokens[position] != "-"
                        or position + 1 >= len(tokens)
                    ):
                        raise _ParseFailure("Convoy destination must follow '-'")
                    order = ConvoyOrder(unit, convoyed, _location(tokens[position + 1], names))
                elif action in {"r", "retreat", "retreats"}:
                    if position >= len(tokens):
                        raise _ParseFailure("Retreat destination is missing")
                    order = RetreatOrder(unit, _location(tokens[position], names))
                elif action in {"b", "build", "builds"}:
                    order = BuildOrder(unit)
                elif action in {"d", "disband", "remove", "removes"}:
                    order = DisbandOrder(unit)
                else:
                    raise _ParseFailure(f"Unknown order action: {tokens[position - 1]}")
        return OrderCandidate(source, order, canonical_text(order, map_definition), ())
    except _ParseFailure as exc:
        issue = Issue("order.unrecognised", str(exc), IssueSeverity.ERROR)
        return OrderCandidate(source, None, None, (issue,))


def parse_orders(
    map_definition: MapDefinition, power_id: PowerId, raw_text: str
) -> tuple[OrderCandidate, ...]:
    return tuple(
        parse_line(map_definition, power_id, SourceLine(number, text))
        for number, text in enumerate(raw_text.splitlines(), 1)
        if text.strip()
    )
