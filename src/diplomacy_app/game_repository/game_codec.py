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
    MapBounds,
    MapDefinition,
    PixelSize,
    SavedView,
    SavedViewId,
    VisibilityPolicy,
)
from diplomacy_app.map_library.map_codec import load_map_folder


def load_game_config(root: Path) -> tuple[GameId, str, GameSettings]:
    try:
        value = yaml.safe_load((root / "game.yaml").read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise InvalidStoredData("Unsupported game.yaml schema")
        fog = value.get("fog_of_war", {})
        orders = value.get("orders", {})
        ui = value.get("ui", {})
        return (
            GameId(str(value["game_id"])),
            str(value["name"]),
            GameSettings(
                VisibilityPolicy(
                    bool(fog.get("enabled", False)), int(fog.get("adjacency_depth", 1))
                ),
                bool(ui.get("explain_adjudication_outcomes", False)),
                bool(orders.get("require_finalisation", False)),
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
        "orders": {"require_finalisation": settings.require_order_finalisation},
        "ui": {"explain_adjudication_outcomes": settings.explain_adjudication_outcomes},
    }
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True)


def load_private_map(root: Path) -> MapDefinition:
    folder = root / "map"
    try:
        return load_map_folder(folder)
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
