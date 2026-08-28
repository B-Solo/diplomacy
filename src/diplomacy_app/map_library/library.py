"""Filesystem-backed reusable map library."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml
from platformdirs import user_data_path

from diplomacy_app.domain.errors import MapLibraryError
from diplomacy_app.domain.models import (
    MapDefinition,
    MapDraft,
    MapId,
    MapPresentation,
    MapSummary,
    MapValidation,
    Point,
    PowerDefinition,
    StartingSetup,
    SvgElementRole,
    TerritoryId,
)
from diplomacy_app.map_library import draft_editor
from diplomacy_app.map_library.map_codec import compile_map, load_map_folder, load_yaml
from diplomacy_app.map_library.svg_importer import (
    element_ids,
    sanitise_svg,
    shape_ids,
    territory_geometries,
)
from diplomacy_app.map_library.validation import validate_map_draft, validate_starting_setup
from diplomacy_app.presentation import (
    DEFAULT_ARMY_HOLD_OFFSET,
    DEFAULT_COAST_LABEL_FONT_SIZE,
    DEFAULT_FLEET_HOLD_OFFSET,
    DEFAULT_INACCESSIBLE_REGION_COLOUR,
    DEFAULT_LABEL_COLOUR,
    DEFAULT_SEA_COLOUR,
    DEFAULT_TERRITORY_LABEL_FONT_SIZE,
    DEFAULT_UNCLAIMED_REGION_COLOUR,
)
from diplomacy_app.storage.serialization import map_definition_data


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _draft_from_folder(path: Path) -> MapDraft:
    text = (path / "map.yaml").read_text(encoding="utf-8")
    document = load_yaml(text)
    assets = document.get("assets", {})
    if not isinstance(assets, dict):
        raise MapLibraryError("assets must be a mapping")
    svg = sanitise_svg((path / str(assets.get("map", "map.svg"))).read_bytes())
    definition = compile_map(text, svg)
    configured_ids = {item.svg_element_id for item in definition.territories}
    non_playable = document.get("non_playable_elements", {})
    roles: dict[str, SvgElementRole] = {}
    for value in element_ids(svg):
        if value in configured_ids:
            roles[value] = SvgElementRole.TERRITORY
        elif isinstance(non_playable, dict) and value in non_playable:
            roles[value] = SvgElementRole(str(non_playable[value]))
    return MapDraft(
        definition.id,
        definition.name,
        svg,
        MappingProxyType(roles),
        definition.territories,
        text,
        definition.powers,
        definition.default_starting_setup,
        definition.presentation,
        definition.rules_engine_id,
    )


def _compiled_payload(definition: MapDefinition) -> dict[str, Any]:
    return map_definition_data(definition)


class FileMapLibrary:
    """Load bundled maps and store user-authored maps in platform data."""

    def __init__(
        self,
        user_maps_root: Path | None = None,
        bundled_maps_root: Path | None = None,
    ) -> None:
        self.user_maps_root = (
            user_maps_root or user_data_path("DiplomacyGamemaster", "DiplomacyGamemaster") / "maps"
        )
        self.bundled_maps_root = bundled_maps_root or _project_root() / "maps"

    def _folders(self) -> dict[MapId, Path]:
        result: dict[MapId, Path] = {}
        for root in (self.bundled_maps_root, self.user_maps_root):
            if not root.exists():
                continue
            for child in sorted(root.iterdir()):
                if child.is_dir() and (child / "map.yaml").is_file():
                    try:
                        document = load_yaml((child / "map.yaml").read_text(encoding="utf-8"))
                        result[MapId(str(document.get("map_id", child.name)))] = child
                    except (OSError, MapLibraryError):
                        continue
        return result

    def list(self) -> tuple[MapSummary, ...]:
        summaries: list[MapSummary] = []
        for map_id, folder in self._folders().items():
            try:
                document = load_yaml((folder / "map.yaml").read_text(encoding="utf-8"))
                teams = document.get("teams", {})
                summaries.append(
                    MapSummary(map_id, str(document.get("name", map_id)), len(teams or {}))
                )
            except (OSError, MapLibraryError) as exc:
                raise MapLibraryError(f"Could not inspect map {folder}: {exc}") from exc
        return tuple(sorted(summaries, key=lambda item: item.name.casefold()))

    def load(self, map_id: MapId) -> MapDefinition:
        folder = self._folders().get(map_id)
        if folder is None:
            raise MapLibraryError(f"Configured map not found: {map_id}")
        try:
            return load_map_folder(folder)
        except (OSError, MapLibraryError) as exc:
            raise MapLibraryError(f"Could not load map {map_id}: {exc}") from exc

    def load_draft(self, map_id: MapId) -> MapDraft:
        folder = self._folders().get(map_id)
        if folder is None:
            raise MapLibraryError(f"Configured map not found: {map_id}")
        return _draft_from_folder(folder)

    def import_svg(self, name: str, svg: bytes) -> MapDraft:
        safe = sanitise_svg(svg)
        map_id = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "new-map"
        geometry_ids = shape_ids(safe)
        playable_ids = tuple(value for value in geometry_ids if value.startswith("territory-"))
        geometries = territory_geometries(safe, playable_ids)
        territories: dict[str, Any] = {}
        label: dict[TerritoryId, Point] = {}
        army: dict[TerritoryId, Point] = {}
        fleet: dict[Any, Point] = {}
        for svg_id in playable_ids:
            territory_id = svg_id.removeprefix("territory-")
            shape = geometries.get(svg_id)
            if shape is None:
                continue
            centre = shape.representative_point()
            abbreviation = "".join(part[:1] for part in territory_id.split("-")[:3]).title()
            abbreviation = (abbreviation + "xxx")[:3]
            territories[territory_id] = {
                "name": territory_id.replace("-", " ").title(),
                "abbreviation": abbreviation,
                "kind": "land",
                "svg_element": svg_id,
                "supply_centre": False,
                "anchors": {
                    "label": [round(centre.x, 2), round(centre.y, 2)],
                    "army": [round(centre.x, 2), round(centre.y, 2)],
                },
            }
            point = Point(float(centre.x), float(centre.y))
            label[TerritoryId(territory_id)] = point
            army[TerritoryId(territory_id)] = point
        non_playable = {value: "decoration" for value in geometry_ids if value not in playable_ids}
        document = {
            "schema_version": 1,
            "map_id": map_id,
            "name": name,
            "rules_engine": "standard",
            "assets": {"map": "map.svg"},
            "presentation": {
                "territory_label_font_size": DEFAULT_TERRITORY_LABEL_FONT_SIZE,
                "coast_label_font_size": DEFAULT_COAST_LABEL_FONT_SIZE,
                "label_colour": DEFAULT_LABEL_COLOUR,
                "inaccessible_region_colour": DEFAULT_INACCESSIBLE_REGION_COLOUR,
                "sea_colour": DEFAULT_SEA_COLOUR,
                "unclaimed_region_colour": DEFAULT_UNCLAIMED_REGION_COLOUR,
                "hold_underlines": {
                    "army": [DEFAULT_ARMY_HOLD_OFFSET.x, DEFAULT_ARMY_HOLD_OFFSET.y],
                    "fleet": [DEFAULT_FLEET_HOLD_OFFSET.x, DEFAULT_FLEET_HOLD_OFFSET.y],
                },
            },
            "start": {"year": 1901, "season": "spring"},
            "teams": {},
            "territories": territories,
            "non_playable_elements": non_playable,
        }
        text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
        definition = compile_map(text, safe)
        roles = {
            value: SvgElementRole.TERRITORY if value in playable_ids else SvgElementRole.DECORATION
            for value in geometry_ids
        }
        return MapDraft(
            MapId(map_id),
            name,
            safe,
            MappingProxyType(roles),
            definition.territories,
            text,
            tuple[PowerDefinition, ...](),
            definition.default_starting_setup,
            MapPresentation(
                MappingProxyType(label),
                MappingProxyType(label),
                MappingProxyType(army),
                MappingProxyType(fleet),
                MappingProxyType({}),
                MappingProxyType({}),
                MappingProxyType({}),
                DEFAULT_TERRITORY_LABEL_FONT_SIZE,
                DEFAULT_COAST_LABEL_FONT_SIZE,
                DEFAULT_LABEL_COLOUR,
                DEFAULT_INACCESSIBLE_REGION_COLOUR,
                DEFAULT_SEA_COLOUR,
                DEFAULT_UNCLAIMED_REGION_COLOUR,
                DEFAULT_ARMY_HOLD_OFFSET,
                DEFAULT_FLEET_HOLD_OFFSET,
            ),
            "standard",
        )

    def validate(self, draft: MapDraft) -> MapValidation:
        return validate_map_draft(draft)

    def refresh_draft(self, draft: MapDraft) -> MapDraft:
        """Rebuild the derived portions of a draft after YAML editing."""
        return draft_editor.refresh_draft(draft)

    def preview_definition(self, draft: MapDraft) -> MapDefinition:
        return compile_map(draft.map_yaml, draft.svg)

    def update_anchor(
        self,
        draft: MapDraft,
        territory_id: TerritoryId,
        anchor: str,
        point: Point,
        coast_id: str | None = None,
    ) -> MapDraft:
        return draft_editor.update_anchor(draft, territory_id, anchor, point, coast_id)

    def update_coast_label_rotation(
        self,
        draft: MapDraft,
        territory_id: TerritoryId,
        coast_id: str,
        rotation: float,
    ) -> MapDraft:
        return draft_editor.update_coast_label_rotation(draft, territory_id, coast_id, rotation)

    def update_element_role(
        self, draft: MapDraft, element_id: str, role: SvgElementRole
    ) -> MapDraft:
        return draft_editor.update_element_role(draft, element_id, role)

    def update_territory_name(
        self, draft: MapDraft, territory_id: TerritoryId, name: str
    ) -> MapDraft:
        return draft_editor.update_territory_name(draft, territory_id, name)

    def update_territory_display_name(
        self, draft: MapDraft, territory_id: TerritoryId, display_name: str
    ) -> MapDraft:
        return draft_editor.update_territory_display_name(draft, territory_id, display_name)

    def update_territory_details(
        self,
        draft: MapDraft,
        territory_id: TerritoryId,
        name: str,
        display_name: str,
        abbreviation: str,
    ) -> MapDraft:
        """Return a draft with all user-facing names for one territory updated.

        :param draft: Authored map draft to update.
        :param territory_id: Stable territory whose names should change.
        :param name: Canonical name accepted by order entry.
        :param display_name: Potentially multiline rendered label.
        :param abbreviation: Unique three-letter order abbreviation.
        :return: Recompiled draft containing the updated territory.
        """
        return draft_editor.update_territory_details(
            draft, territory_id, name, display_name, abbreviation
        )

    def update_setup(
        self,
        draft: MapDraft,
        powers: tuple[PowerDefinition, ...],
        starting_setup: StartingSetup,
    ) -> MapDraft:
        """Return a draft containing the supplied powers and starting state.

        :param draft: Authored map draft to update.
        :param powers: Complete ordered power definitions.
        :param starting_setup: Complete starting phase and state.
        :return: Recompiled draft containing the updated setup.
        """
        return draft_editor.update_setup(draft, powers, starting_setup)

    def update_label_font_sizes(
        self, draft: MapDraft, territory_size: float, coast_size: float
    ) -> MapDraft:
        return draft_editor.update_label_font_sizes(draft, territory_size, coast_size)

    def update_hold_offsets(
        self, draft: MapDraft, army_offset: Point, fleet_offset: Point
    ) -> MapDraft:
        """Return a draft with map-wide army and fleet hold offsets."""
        return draft_editor.update_hold_offsets(draft, army_offset, fleet_offset)

    def update_map_colours(
        self,
        draft: MapDraft,
        label_colour: str,
        inaccessible_colour: str,
        sea_colour: str,
        unclaimed_colour: str,
    ) -> MapDraft:
        return draft_editor.update_map_colours(
            draft,
            label_colour,
            inaccessible_colour,
            sea_colour,
            unclaimed_colour,
        )

    def validate_starting_setup(
        self, map_definition: MapDefinition, starting_setup: StartingSetup
    ) -> MapValidation:
        return validate_starting_setup(map_definition, starting_setup)

    def save(self, draft: MapDraft) -> MapDefinition:
        validation = self.validate(draft)
        if not validation.is_valid:
            messages = "; ".join(item.issue.message for item in validation.issues)
            raise MapLibraryError(f"Map has validation errors: {messages}")
        definition = compile_map(draft.map_yaml, draft.svg)
        self.user_maps_root.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=f".{definition.id}-", dir=self.user_maps_root))
        (stage / "map.yaml").write_text(draft.map_yaml, encoding="utf-8")
        (stage / "map.svg").write_bytes(definition.assets.map_svg)
        (stage / "army.svg").write_bytes(definition.assets.army_svg)
        (stage / "fleet.svg").write_bytes(definition.assets.fleet_svg)
        (stage / "_compiled-map.json").write_text(
            json.dumps(_compiled_payload(definition), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        target = self.user_maps_root / str(definition.id)
        backup = self.user_maps_root / f".{definition.id}.backup"
        try:
            if backup.exists():
                shutil.rmtree(backup)
            if target.exists():
                os.replace(target, backup)
            os.replace(stage, target)
            if backup.exists():
                shutil.rmtree(backup)
        except OSError as exc:
            if not target.exists() and backup.exists():
                os.replace(backup, target)
            raise MapLibraryError(f"Could not save map {definition.id}: {exc}") from exc
        return definition
