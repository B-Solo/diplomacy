"""Game-folder configuration and map snapshot codecs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from diplomacy_app.domain.errors import InvalidStoredData
from diplomacy_app.domain.models import (
    GameId,
    GameSettings,
    Location,
    MapAssets,
    MapBounds,
    MapDefinition,
    PixelSize,
    SavedView,
    SavedViewId,
    VisibilityPolicy,
)
from diplomacy_app.map_library.defaults import DEFAULT_ARMY_SVG, DEFAULT_FLEET_SVG
from diplomacy_app.storage.serialization import map_definition_from_data


def load_game_config(root: Path) -> tuple[GameId, str, GameSettings]:
    try:
        value = yaml.safe_load((root / "game.yaml").read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise InvalidStoredData("Unsupported game.yaml schema")
        fog = value.get("fog_of_war", {})
        ui = value.get("ui", {})
        return (
            GameId(str(value["game_id"])),
            str(value["name"]),
            GameSettings(
                VisibilityPolicy(
                    bool(fog.get("enabled", False)), int(fog.get("adjacency_depth", 1))
                ),
                bool(ui.get("explain_adjudication_outcomes", False)),
            ),
        )
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        if isinstance(exc, InvalidStoredData):
            raise
        raise InvalidStoredData(f"Invalid game.yaml: {exc}") from exc


def game_config_data(game_id: GameId, name: str, settings: GameSettings) -> str:
    value = {
        "schema_version": 1,
        "game_id": game_id,
        "name": name,
        "fog_of_war": {
            "enabled": settings.visibility_policy.enabled,
            "adjacency_depth": settings.visibility_policy.adjacency_depth,
        },
        "ui": {"explain_adjudication_outcomes": settings.explain_adjudication_outcomes},
    }
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True)


def load_private_map(root: Path) -> MapDefinition:
    folder = root / "map"
    try:
        assets = MapAssets(
            (folder / "map.svg").read_bytes(),
            DEFAULT_ARMY_SVG,
            DEFAULT_FLEET_SVG,
        )
        value = json.loads((folder / "_compiled-map.json").read_text(encoding="utf-8"))
        return map_definition_from_data(value, assets)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, InvalidStoredData):
            raise
        raise InvalidStoredData(f"Invalid private map snapshot: {exc}") from exc


def views_data(views: tuple[SavedView, ...]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "views": [
            {
                "id": item.id,
                "name": item.name,
                "bounds": [item.bounds.x, item.bounds.y, item.bounds.width, item.bounds.height],
                "aspect_ratio": item.aspect_ratio,
                "output_size": [item.output_size.width, item.output_size.height],
            }
            for item in views
        ],
    }


def load_views(root: Path) -> tuple[SavedView, ...]:
    path = root / "views.json"
    if not path.exists():
        return ()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema_version") != 1:
            raise InvalidStoredData("Unsupported views schema")
        return tuple(
            SavedView(
                SavedViewId(str(item["id"])),
                str(item["name"]),
                MapBounds(*map(float, item["bounds"])),
                float(item["aspect_ratio"]),
                PixelSize(*map(int, item["output_size"])),
            )
            for item in value.get("views", [])
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, InvalidStoredData):
            raise
        raise InvalidStoredData(f"Invalid views.json: {exc}") from exc


def authored_map_yaml(definition: MapDefinition) -> str:
    """Materialise a human-readable private-map source beside compiled data."""
    teams: dict[str, Any] = {}
    setup = definition.default_starting_setup.state
    for power in definition.powers:
        teams[str(power.id)] = {
            "name": power.name,
            "colour": power.colour,
            "home_supply_centres": sorted(power.home_supply_centres),
            "starting_supply_centres": sorted(
                key for key, owner in setup.supply_centre_owners.items() if owner == power.id
            ),
            "starting_territories": sorted(
                key for key, owner in setup.territory_controllers.items() if owner == power.id
            ),
            "initial_units": [
                {
                    "type": unit.unit_type.value,
                    "location": str(unit.location.territory_id)
                    + (f"/{unit.location.coast_id}" if unit.location.coast_id else ""),
                }
                for unit in setup.units
                if unit.power_id == power.id
            ],
        }
    territories: dict[str, Any] = {}
    for territory in definition.territories:
        anchors: dict[str, list[float]] = {}
        if territory.id in definition.presentation.label_anchors:
            point = definition.presentation.label_anchors[territory.id]
            anchors["label"] = [point.x, point.y]
        if territory.id in definition.presentation.abbreviation_anchors:
            point = definition.presentation.abbreviation_anchors[territory.id]
            anchors["abbreviation"] = [point.x, point.y]
        if territory.id in definition.presentation.army_anchors:
            point = definition.presentation.army_anchors[territory.id]
            anchors["army"] = [point.x, point.y]
        fleet_location = next(
            (
                location
                for location in definition.presentation.fleet_anchors
                if location.territory_id == territory.id and location.coast_id is None
            ),
            None,
        )
        if fleet_location:
            point = definition.presentation.fleet_anchors[fleet_location]
            anchors["fleet"] = [point.x, point.y]
        if territory.id in definition.presentation.supply_centre_anchors:
            point = definition.presentation.supply_centre_anchors[territory.id]
            anchors["supply_centre"] = [point.x, point.y]
        item: dict[str, Any] = {
            "name": territory.name,
            "display_name": territory.display_name,
            "abbreviation": territory.abbreviation,
            "kind": territory.kind.value,
            "svg_element": territory.svg_element_id,
            "supply_centre": territory.is_supply_centre,
            "anchors": anchors,
        }
        if territory.split_coast_ids:
            item["split_coasts"] = {
                str(coast): {
                    "fleet_anchor": [
                        definition.presentation.fleet_anchors[location].x,
                        definition.presentation.fleet_anchors[location].y,
                    ],
                    "label_anchor": [
                        definition.presentation.coast_label_anchors[location].x,
                        definition.presentation.coast_label_anchors[location].y,
                    ],
                    "label_rotation": definition.presentation.coast_label_rotations.get(
                        location, 0
                    ),
                    "add_connections": sorted(
                        {
                            edge.destination.territory_id
                            for edge in definition.adjacencies
                            if edge.origin == location
                        }
                    ),
                }
                for coast in territory.split_coast_ids
                for location in [Location(territory.id, coast)]
            }
        territories[str(territory.id)] = item
    value = {
        "schema_version": 1,
        "map_id": definition.id,
        "name": definition.name,
        "rules_engine": definition.rules_engine_id,
        "assets": {"map": "map.svg", "army": "army.svg", "fleet": "fleet.svg"},
        "presentation": {
            "territory_label_font_size": definition.presentation.territory_label_font_size,
            "coast_label_font_size": definition.presentation.coast_label_font_size,
            "label_colour": definition.presentation.label_colour,
            "inaccessible_region_colour": definition.presentation.inaccessible_region_colour,
            "sea_colour": definition.presentation.sea_colour,
            "unclaimed_region_colour": definition.presentation.unclaimed_region_colour,
        },
        "start": {
            "year": definition.default_starting_setup.phase_id.year,
            "season": definition.default_starting_setup.phase_id.season.value,
        },
        "teams": teams,
        "territories": territories,
        "non_playable_elements": {
            element_id: "impassable"
            for element_id in sorted(definition.inaccessible_svg_element_ids)
        },
    }
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
