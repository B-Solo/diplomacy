"""Authored map YAML parsing and effective-topology compilation."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from diplomacy_app.domain.errors import MapLibraryError
from diplomacy_app.domain.models import (
    Adjacency,
    CoastId,
    DislodgedUnit,
    GameState,
    Location,
    MapAssets,
    MapDefinition,
    MapId,
    MapPresentation,
    PhaseId,
    Point,
    PowerDefinition,
    PowerId,
    Season,
    StartingSetup,
    SvgElementRole,
    TerritoryDefinition,
    TerritoryId,
    TerritoryKind,
    UnitPosition,
    UnitType,
)
from diplomacy_app.map_library.defaults import DEFAULT_ARMY_SVG, DEFAULT_FLEET_SVG
from diplomacy_app.map_library.geometry import inferred_connections
from diplomacy_app.map_library.svg_importer import sanitise_svg, territory_geometries
from diplomacy_app.presentation import (
    DEFAULT_ARMY_HOLD_OFFSET,
    DEFAULT_COAST_LABEL_FONT_SIZE,
    DEFAULT_FLEET_HOLD_OFFSET,
    DEFAULT_INACCESSIBLE_REGION_COLOUR,
    DEFAULT_LABEL_COLOUR,
    DEFAULT_SEA_COLOUR,
    DEFAULT_TERRITORY_LABEL_FONT_SIZE,
    DEFAULT_UNCLAIMED_REGION_COLOUR,
    default_coast_label_anchor,
)

_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")


def load_yaml(text: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MapLibraryError(f"Invalid map YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise MapLibraryError("Map YAML must contain an object at its root")
    if value.get("schema_version") != 1:
        raise MapLibraryError("Only map schema_version 1 is supported")
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise MapLibraryError(f"{field} must be a mapping")
    return value


def _point(value: object, field: str) -> Point:
    if not isinstance(value, list) or len(value) != 2:
        raise MapLibraryError(f"{field} must contain [x, y]")
    try:
        return Point(float(value[0]), float(value[1]))
    except (TypeError, ValueError) as exc:
        raise MapLibraryError(f"{field} must contain numeric coordinates") from exc


def _location(value: str, territories: Mapping[str, TerritoryDefinition]) -> Location:
    base, separator, coast = value.partition("/")
    if base not in territories:
        raise MapLibraryError(f"Unknown territory location: {base}")
    coast_id = CoastId(coast) if separator else None
    if coast_id is not None and coast_id not in territories[base].split_coast_ids:
        raise MapLibraryError(f"Unknown coast location: {value}")
    return Location(TerritoryId(base), coast_id)


def _parse_territories(raw: Mapping[str, Any]) -> tuple[TerritoryDefinition, ...]:
    result: list[TerritoryDefinition] = []
    for territory_id, untyped in raw.items():
        item = _mapping(untyped, f"territories.{territory_id}")
        split = _mapping(item.get("split_coasts", {}), f"territories.{territory_id}.split_coasts")
        result.append(
            TerritoryDefinition(
                id=TerritoryId(territory_id),
                name=str(item.get("name", territory_id)),
                display_name=str(item.get("display_name", item.get("name", territory_id))),
                abbreviation=str(item.get("abbreviation", "")),
                kind=TerritoryKind(str(item.get("kind", "land"))),
                svg_element_id=str(item.get("svg_element", "")),
                split_coast_ids=tuple(CoastId(value) for value in split),
                is_supply_centre=bool(item.get("supply_centre", False)),
            )
        )
    return tuple(result)


def _parse_presentation(
    raw: Mapping[str, Any],
    territories: tuple[TerritoryDefinition, ...],
    settings: Mapping[str, Any],
) -> MapPresentation:
    label: dict[TerritoryId, Point] = {}
    abbreviation: dict[TerritoryId, Point] = {}
    army: dict[TerritoryId, Point] = {}
    fleet: dict[Location, Point] = {}
    coast_labels: dict[Location, Point] = {}
    coast_rotations: dict[Location, float] = {}
    supply: dict[TerritoryId, Point] = {}
    for territory in territories:
        item = _mapping(raw[str(territory.id)], f"territories.{territory.id}")
        anchors = _mapping(item.get("anchors", {}), f"territories.{territory.id}.anchors")
        if "label" in anchors:
            label[territory.id] = _point(anchors["label"], f"{territory.id}.anchors.label")
            abbreviation[territory.id] = (
                _point(
                    anchors["abbreviation"],
                    f"{territory.id}.anchors.abbreviation",
                )
                if "abbreviation" in anchors
                else label[territory.id]
            )
        if "army" in anchors:
            army[territory.id] = _point(anchors["army"], f"{territory.id}.anchors.army")
        if "fleet" in anchors:
            fleet[Location(territory.id)] = _point(
                anchors["fleet"], f"{territory.id}.anchors.fleet"
            )
        if "supply_centre" in anchors:
            supply[territory.id] = _point(
                anchors["supply_centre"], f"{territory.id}.anchors.supply_centre"
            )
        split = _mapping(item.get("split_coasts", {}), f"territories.{territory.id}.split_coasts")
        for coast_id, coast_value in split.items():
            coast = _mapping(coast_value, f"territories.{territory.id}.split_coasts.{coast_id}")
            if "fleet_anchor" in coast:
                location = Location(territory.id, CoastId(coast_id))
                fleet_anchor = _point(
                    coast["fleet_anchor"], f"{territory.id}.{coast_id}.fleet_anchor"
                )
                fleet[location] = fleet_anchor
                coast_labels[location] = (
                    _point(coast["label_anchor"], f"{territory.id}.{coast_id}.label_anchor")
                    if "label_anchor" in coast
                    else default_coast_label_anchor(CoastId(coast_id), fleet_anchor)
                )
                try:
                    coast_rotations[location] = float(coast.get("label_rotation", 0))
                except (TypeError, ValueError) as exc:
                    raise MapLibraryError(
                        f"{territory.id}.{coast_id}.label_rotation must be numeric"
                    ) from exc
    try:
        territory_font_size = float(
            settings.get("territory_label_font_size", DEFAULT_TERRITORY_LABEL_FONT_SIZE)
        )
        coast_font_size = float(
            settings.get("coast_label_font_size", DEFAULT_COAST_LABEL_FONT_SIZE)
        )
    except (TypeError, ValueError) as exc:
        raise MapLibraryError("Presentation font sizes must be numeric") from exc
    if not all(
        math.isfinite(size) and 5 <= size <= 24 for size in (territory_font_size, coast_font_size)
    ):
        raise MapLibraryError("Presentation font sizes must be between 5 and 24")
    colours = (
        str(settings.get("label_colour", DEFAULT_LABEL_COLOUR)),
        str(settings.get("inaccessible_region_colour", DEFAULT_INACCESSIBLE_REGION_COLOUR)),
        str(settings.get("sea_colour", DEFAULT_SEA_COLOUR)),
        str(settings.get("unclaimed_region_colour", DEFAULT_UNCLAIMED_REGION_COLOUR)),
    )
    if not all(_COLOUR.fullmatch(colour) for colour in colours):
        raise MapLibraryError("Presentation colours must use #RRGGBB notation")
    hold_underlines = _mapping(settings.get("hold_underlines", {}), "presentation.hold_underlines")
    army_hold_offset = _point(
        hold_underlines.get("army", [DEFAULT_ARMY_HOLD_OFFSET.x, DEFAULT_ARMY_HOLD_OFFSET.y]),
        "presentation.hold_underlines.army",
    )
    fleet_hold_offset = _point(
        hold_underlines.get("fleet", [DEFAULT_FLEET_HOLD_OFFSET.x, DEFAULT_FLEET_HOLD_OFFSET.y]),
        "presentation.hold_underlines.fleet",
    )
    if not all(
        -50 <= coordinate <= 50
        for point in (army_hold_offset, fleet_hold_offset)
        for coordinate in (point.x, point.y)
    ):
        raise MapLibraryError("Hold underline offsets must be between -50 and 50")
    return MapPresentation(
        MappingProxyType(label),
        MappingProxyType(abbreviation),
        MappingProxyType(army),
        MappingProxyType(fleet),
        MappingProxyType(coast_labels),
        MappingProxyType(coast_rotations),
        MappingProxyType(supply),
        territory_font_size,
        coast_font_size,
        *colours,
        army_hold_offset,
        fleet_hold_offset,
    )


def _effective_connections(
    raw: Mapping[str, Any],
    territories: tuple[TerritoryDefinition, ...],
    svg: bytes,
) -> frozenset[Adjacency]:
    by_id = {str(item.id): item for item in territories}
    geometry = territory_geometries(svg, (item.svg_element_id for item in territories))
    inferred = {
        pair: set(units) for pair, units in inferred_connections(territories, geometry).items()
    }
    for origin_id, untyped in raw.items():
        item = _mapping(untyped, f"territories.{origin_id}")
        overrides = _mapping(
            item.get("connection_overrides", {}),
            f"territories.{origin_id}.connection_overrides",
        )
        for operation in ("add", "remove"):
            entries = overrides.get(operation, [])
            if not isinstance(entries, list):
                raise MapLibraryError(
                    f"{origin_id}.connection_overrides.{operation} must be a list"
                )
            for entry_value in entries:
                entry = _mapping(entry_value, f"{origin_id}.connection_overrides.{operation}")
                destination = str(entry.get("to", ""))
                if destination not in by_id:
                    raise MapLibraryError(f"Unknown connection destination: {destination}")
                pair = frozenset((TerritoryId(origin_id), TerritoryId(destination)))
                units_value = entry.get("units", [])
                if not isinstance(units_value, list):
                    raise MapLibraryError(f"Connection units for {origin_id} must be a list")
                units = {str(value) for value in units_value}
                if operation == "add":
                    inferred.setdefault(pair, set()).update(units)
                else:
                    inferred.setdefault(pair, set()).difference_update(units)

    adjacencies: set[Adjacency] = set()
    for pair, units in inferred.items():
        if len(pair) != 2:
            continue
        left, right = sorted(pair)
        for unit_name in units:
            unit = UnitType(unit_name)
            # Fleet inference is replaced by explicit named coast connections.
            if unit is UnitType.FLEET and (
                by_id[str(left)].split_coast_ids or by_id[str(right)].split_coast_ids
            ):
                continue
            adjacencies.add(Adjacency(Location(left), Location(right), unit))
            adjacencies.add(Adjacency(Location(right), Location(left), unit))

    for origin_id, untyped in raw.items():
        item = _mapping(untyped, f"territories.{origin_id}")
        split = _mapping(item.get("split_coasts", {}), f"territories.{origin_id}.split_coasts")
        for coast_id, coast_value in split.items():
            coast = _mapping(coast_value, f"territories.{origin_id}.split_coasts.{coast_id}")
            connections = coast.get("add_connections", [])
            if not isinstance(connections, list):
                raise MapLibraryError(f"{origin_id}.{coast_id}.add_connections must be a list")
            coast_location = Location(TerritoryId(origin_id), CoastId(coast_id))
            for destination_id in connections:
                destination_location = Location(TerritoryId(str(destination_id)))
                if str(destination_location.territory_id) not in by_id:
                    raise MapLibraryError(f"Unknown split-coast destination: {destination_id}")
                adjacencies.add(Adjacency(coast_location, destination_location, UnitType.FLEET))
                adjacencies.add(Adjacency(destination_location, coast_location, UnitType.FLEET))
    return frozenset(adjacencies)


def _parse_powers_and_start(
    document: Mapping[str, Any], territories: tuple[TerritoryDefinition, ...]
) -> tuple[tuple[PowerDefinition, ...], StartingSetup]:
    territory_by_id = {str(item.id): item for item in territories}
    teams = _mapping(document.get("teams", {}), "teams")
    powers: list[PowerDefinition] = []
    units: list[UnitPosition] = []
    dislodged: list[DislodgedUnit] = []
    controllers: dict[TerritoryId, PowerId | None] = {item.id: None for item in territories}
    owners: dict[TerritoryId, PowerId | None] = {
        item.id: None for item in territories if item.is_supply_centre
    }
    for power_id, untyped in teams.items():
        item = _mapping(untyped, f"teams.{power_id}")
        power = PowerId(power_id)
        home = frozenset(TerritoryId(str(value)) for value in item.get("home_supply_centres", []))
        powers.append(
            PowerDefinition(
                power, str(item.get("name", power_id)), str(item.get("colour", "#777777")), home
            )
        )
        for territory_id in item.get("starting_supply_centres", []):
            owners[TerritoryId(str(territory_id))] = power
        for territory_id in item.get("starting_territories", []):
            controllers[TerritoryId(str(territory_id))] = power
        for unit_value in item.get("initial_units", []):
            unit = _mapping(unit_value, f"teams.{power_id}.initial_units")
            location = _location(str(unit.get("location", "")), territory_by_id)
            units.append(UnitPosition(power, UnitType(str(unit.get("type", ""))), location))
        for unit_value in item.get("initial_dislodged_units", []):
            unit = _mapping(unit_value, f"teams.{power_id}.initial_dislodged_units")
            position = UnitPosition(
                power,
                UnitType(str(unit.get("type", ""))),
                _location(str(unit.get("location", "")), territory_by_id),
            )
            options = tuple(
                _location(str(value), territory_by_id) for value in unit.get("retreat_options", [])
            )
            dislodged.append(DislodgedUnit(position, options))
    start = _mapping(document.get("start", {}), "start")
    phase = PhaseId(int(start.get("year", 1901)), Season(str(start.get("season", "spring"))))
    state = GameState(
        tuple(units),
        tuple(dislodged),
        MappingProxyType(controllers),
        MappingProxyType(owners),
    )
    return tuple(powers), StartingSetup(phase, state)


def compile_map(
    text: str,
    svg: bytes,
) -> MapDefinition:
    """Compile authored map content into a validated application snapshot."""
    document = load_yaml(text)
    safe_svg = sanitise_svg(svg)
    raw_territories = _mapping(document.get("territories", {}), "territories")
    territories = _parse_territories(raw_territories)
    powers, setup = _parse_powers_and_start(document, territories)
    presentation_settings = _mapping(document.get("presentation", {}), "presentation")
    presentation = _parse_presentation(raw_territories, territories, presentation_settings)
    non_playable = _mapping(document.get("non_playable_elements", {}), "non_playable_elements")
    inaccessible_ids = frozenset(
        str(element_id)
        for element_id, role in non_playable.items()
        if str(role) == SvgElementRole.IMPASSABLE.value
    )
    topology = _effective_connections(raw_territories, territories, safe_svg)
    return MapDefinition(
        id=MapId(str(document.get("map_id", ""))),
        name=str(document.get("name", "")),
        territories=territories,
        adjacencies=topology,
        powers=powers,
        default_starting_setup=setup,
        presentation=presentation,
        inaccessible_svg_element_ids=inaccessible_ids,
        assets=MapAssets(safe_svg, DEFAULT_ARMY_SVG, DEFAULT_FLEET_SVG),
        rules_engine_id=str(document.get("rules_engine", "standard")),
    )


def load_map_folder(path: Path) -> MapDefinition:
    text = (path / "map.yaml").read_text(encoding="utf-8")
    document = load_yaml(text)
    assets = _mapping(document.get("assets", {}), "assets")
    map_path = path / str(assets.get("map", "map.svg"))
    return compile_map(text, map_path.read_bytes())
