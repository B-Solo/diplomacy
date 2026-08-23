"""Translate typed application orders to bundled-engine notation."""

from __future__ import annotations

from diplomacy_app.domain.models import (
    BuildOrder,
    CanonicalOrder,
    ConvoyOrder,
    DisbandOrder,
    HoldOrder,
    Location,
    MapDefinition,
    MoveOrder,
    RetreatOrder,
    SupportOrder,
    UnitRef,
    UnitType,
    WaiveOrder,
)
from diplomacy_app.rules_engine.map_adapter import abbreviation_indexes


def _unit(value: UnitRef, names: dict[Location, str]) -> str:
    kind = "A" if value.unit_type is UnitType.ARMY else "F"
    return f"{kind} {names[value.location]}"


def to_engine_order(map_definition: MapDefinition, order: CanonicalOrder) -> str:
    _, names = abbreviation_indexes(map_definition)
    if isinstance(order, WaiveOrder):
        return "WAIVE"
    unit = _unit(order.unit, names)
    if isinstance(order, HoldOrder):
        return f"{unit} H"
    if isinstance(order, MoveOrder):
        convoy = " VIA" if order.via_convoy else ""
        return f"{unit} - {names[order.destination]}{convoy}"
    if isinstance(order, SupportOrder):
        supported = _unit(order.supported_unit, names)
        destination = f" - {names[order.destination]}" if order.destination else ""
        return f"{unit} S {supported}{destination}"
    if isinstance(order, ConvoyOrder):
        return f"{unit} C {_unit(order.convoyed_army, names)} - {names[order.destination]}"
    if isinstance(order, RetreatOrder):
        return f"{unit} R {names[order.destination]}"
    if isinstance(order, BuildOrder):
        return f"{unit} B"
    if isinstance(order, DisbandOrder):
        return f"{unit} D"
    raise TypeError(type(order).__name__)
