"""Application-owned last-opened and recent-game catalogue."""

from __future__ import annotations

import json
from pathlib import Path

from platformdirs import user_config_path

from diplomacy_app.domain.models import GameLocation
from diplomacy_app.game_repository.transaction import atomic_json


class RecentGameStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (
            path
            or user_config_path("DiplomacyGamemaster", "DiplomacyGamemaster") / "application.json"
        )

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {"schema_version": 1, "last_opened": None, "recent_games": []}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("schema_version") != 1:
                return {"schema_version": 1, "last_opened": None, "recent_games": []}
            return value
        except (OSError, json.JSONDecodeError):
            return {"schema_version": 1, "last_opened": None, "recent_games": []}

    def locations(self) -> tuple[GameLocation, ...]:
        value = self._read().get("recent_games", [])
        if not isinstance(value, list):
            return ()
        result: list[GameLocation] = []
        for item in value:
            try:
                result.append(GameLocation(Path(str(item)).resolve()))
            except ValueError:
                continue
        return tuple(result)

    def last_opened(self) -> GameLocation | None:
        value = self._read().get("last_opened")
        return GameLocation(Path(str(value)).resolve()) if value else None

    def record(self, location: GameLocation) -> None:
        current = [item.path for item in self.locations() if item.path != location.path]
        recent = [location.path, *current][:20]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(
            self.path,
            {
                "schema_version": 1,
                "last_opened": str(location.path),
                "recent_games": [str(path) for path in recent],
            },
        )
