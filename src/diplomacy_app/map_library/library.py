"""Filesystem-backed reusable map library."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml
from platformdirs import user_data_path

from diplomacy_app.domain.errors import MapLibraryError
from diplomacy_app.domain.models import (
    Issue,
    IssueLocation,
    IssueSeverity,
    LocatedIssue,
    MapDefinition,
    MapDraft,
    MapId,
    MapPresentation,
    MapSummary,
    MapValidation,
    Point,
    PowerDefinition,
    Season,
    StartingSetup,
    SvgElementRole,
    TerritoryId,
    TerritoryKind,
)
from diplomacy_app.map_library.map_codec import compile_map, load_map_folder, load_yaml
from diplomacy_app.map_library.svg_importer import (
    element_ids,
    sanitise_svg,
    shape_ids,
    territory_geometries,
)
from diplomacy_app.presentation import (
    DEFAULT_COAST_LABEL_FONT_SIZE,
    DEFAULT_INACCESSIBLE_REGION_COLOUR,
    DEFAULT_LABEL_COLOUR,
    DEFAULT_SEA_COLOUR,
    DEFAULT_TERRITORY_LABEL_FONT_SIZE,
    DEFAULT_UNCLAIMED_REGION_COLOUR,
)
from diplomacy_app.storage.serialization import map_definition_data

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ABBREVIATION = re.compile(r"^[A-Za-z]{3}$")


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
            ),
            "standard",
        )

    def validate(self, draft: MapDraft) -> MapValidation:
        issues: list[LocatedIssue] = []

        def error(code: str, message: str, field: str, item_id: str | None = None) -> None:
            issues.append(
                LocatedIssue(
                    Issue(code, message, IssueSeverity.ERROR),
                    IssueLocation(field, item_id),
                )
            )

        try:
            definition = compile_map(draft.map_yaml, draft.svg)
        except MapLibraryError as exc:
            error("map.invalid", str(exc), "map_yaml")
            return MapValidation(tuple(issues))
        if not _SLUG.fullmatch(str(definition.id)):
            error("map.invalid_id", "Map ID must be a lowercase stable slug", "map_id")
        if not definition.name.strip():
            error("map.missing_name", "Map name is required", "name")
        svg_ids = set(element_ids(definition.assets.map_svg))
        seen_abbreviations: set[str] = set()
        seen_ids: set[TerritoryId] = set()
        for territory in definition.territories:
            if territory.id in seen_ids:
                error(
                    "territory.duplicate_id",
                    "Territory ID is duplicated",
                    "territories",
                    str(territory.id),
                )
            seen_ids.add(territory.id)
            if not territory.name.strip():
                error(
                    "territory.missing_name",
                    "Canonical territory name is required",
                    "name",
                    str(territory.id),
                )
            if not territory.display_name.strip():
                error(
                    "territory.missing_display_name",
                    "Territory display name is required",
                    "display_name",
                    str(territory.id),
                )
            abbreviation = territory.abbreviation.casefold()
            if not _ABBREVIATION.fullmatch(territory.abbreviation):
                error(
                    "territory.invalid_abbreviation",
                    "Abbreviation must be exactly three ASCII letters",
                    "abbreviation",
                    str(territory.id),
                )
            if abbreviation in seen_abbreviations:
                error(
                    "territory.duplicate_abbreviation",
                    "Territory abbreviation is not unique",
                    "abbreviation",
                    str(territory.id),
                )
            seen_abbreviations.add(abbreviation)
            if territory.svg_element_id not in svg_ids:
                error(
                    "territory.missing_svg_element",
                    "Referenced SVG element does not exist",
                    "svg_element",
                    str(territory.id),
                )
            if territory.id not in definition.presentation.label_anchors:
                error(
                    "territory.missing_label_anchor",
                    "Label anchor is required",
                    "anchors.label",
                    str(territory.id),
                )
            if territory.id not in definition.presentation.abbreviation_anchors:
                error(
                    "territory.missing_abbreviation_anchor",
                    "Territory abbreviation anchor is required",
                    "anchors.abbreviation",
                    str(territory.id),
                )
            if (
                territory.kind is TerritoryKind.LAND
                and territory.id not in definition.presentation.army_anchors
            ):
                error(
                    "territory.missing_army_anchor",
                    "Land territory requires an army anchor",
                    "anchors.army",
                    str(territory.id),
                )
            if (
                territory.is_supply_centre
                and territory.id not in definition.presentation.supply_centre_anchors
            ):
                error(
                    "territory.missing_supply_anchor",
                    "Supply centre requires a star anchor",
                    "anchors.supply_centre",
                    str(territory.id),
                )
        known_powers = {power.id for power in definition.powers}
        for unit in definition.default_starting_setup.state.units:
            if unit.power_id not in known_powers:
                error("start.unknown_power", "Starting unit has an unknown power", "start.units")
        if definition.rules_engine_id != "standard":
            error(
                "map.unknown_engine",
                f"Unknown rules engine: {definition.rules_engine_id}",
                "rules_engine",
            )
        return MapValidation(tuple(issues))

    def refresh_draft(self, draft: MapDraft) -> MapDraft:
        """Rebuild the derived portions of a draft after YAML editing."""
        definition = compile_map(draft.map_yaml, draft.svg)
        return replace(
            draft,
            map_id=definition.id,
            name=definition.name,
            territories=definition.territories,
            powers=definition.powers,
            default_starting_setup=definition.default_starting_setup,
            presentation=definition.presentation,
            rules_engine_id=definition.rules_engine_id,
        )

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
        document = load_yaml(draft.map_yaml)
        territories = document.get("territories", {})
        item = territories.get(str(territory_id))
        if not isinstance(item, dict):
            raise MapLibraryError(f"Unknown territory: {territory_id}")
        if coast_id:
            split = item.setdefault("split_coasts", {})
            coast = split.setdefault(coast_id, {})
            field = "label_anchor" if anchor == "coast_label" else "fleet_anchor"
            coast[field] = [round(point.x, 2), round(point.y, 2)]
        else:
            anchors = item.setdefault("anchors", {})
            anchors[anchor] = [round(point.x, 2), round(point.y, 2)]
        text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
        return self.refresh_draft(replace(draft, map_yaml=text))

    def update_coast_label_rotation(
        self,
        draft: MapDraft,
        territory_id: TerritoryId,
        coast_id: str,
        rotation: float,
    ) -> MapDraft:
        document = load_yaml(draft.map_yaml)
        territories = document.get("territories", {})
        item = territories.get(str(territory_id))
        if not isinstance(item, dict):
            raise MapLibraryError(f"Unknown territory: {territory_id}")
        split = item.setdefault("split_coasts", {})
        coast = split.get(coast_id)
        if not isinstance(coast, dict):
            raise MapLibraryError(f"Unknown split coast: {territory_id}/{coast_id}")
        coast["label_rotation"] = round(rotation, 2)
        text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
        return self.refresh_draft(replace(draft, map_yaml=text))

    def update_element_role(
        self, draft: MapDraft, element_id: str, role: SvgElementRole
    ) -> MapDraft:
        document = load_yaml(draft.map_yaml)
        territories = document.setdefault("territories", {})
        non_playable = document.setdefault("non_playable_elements", {})
        for key, value in tuple(territories.items()):
            if isinstance(value, dict) and value.get("svg_element") == element_id:
                if role is not SvgElementRole.TERRITORY:
                    del territories[key]
                break
        if role is SvgElementRole.TERRITORY:
            non_playable.pop(element_id, None)
            if not any(
                isinstance(value, dict) and value.get("svg_element") == element_id
                for value in territories.values()
            ):
                base_id = re.sub(r"[^a-z0-9]+", "-", element_id.casefold()).strip("-")
                base_id = base_id.removeprefix("territory-") or "territory"
                territory_id = base_id
                suffix = 2
                while territory_id in territories:
                    territory_id = f"{base_id}-{suffix}"
                    suffix += 1
                geometry = territory_geometries(draft.svg, [element_id]).get(element_id)
                x, y = (0.0, 0.0)
                if geometry is not None:
                    centre = geometry.representative_point()
                    x, y = float(centre.x), float(centre.y)
                used = {
                    str(value.get("abbreviation", "")).casefold()
                    for value in territories.values()
                    if isinstance(value, dict)
                }
                abbreviation = ("".join(part[:1] for part in territory_id.split("-")) + "xxx")[:3]
                attempt = abbreviation
                number = 0
                while attempt.casefold() in used:
                    attempt = f"{abbreviation[:2]}{chr(ord('a') + number % 26)}"
                    number += 1
                territories[territory_id] = {
                    "name": territory_id.replace("-", " ").title(),
                    "abbreviation": attempt.title(),
                    "kind": "land",
                    "svg_element": element_id,
                    "supply_centre": False,
                    "anchors": {"label": [x, y], "army": [x, y]},
                }
        else:
            non_playable[element_id] = role.value
        roles = dict(draft.element_roles)
        roles[element_id] = role
        text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
        return self.refresh_draft(
            replace(draft, map_yaml=text, element_roles=MappingProxyType(roles))
        )

    def update_territory_name(
        self, draft: MapDraft, territory_id: TerritoryId, name: str
    ) -> MapDraft:
        document = load_yaml(draft.map_yaml)
        territories = document.get("territories", {})
        item = territories.get(str(territory_id))
        if not isinstance(item, dict):
            raise MapLibraryError(f"Unknown territory: {territory_id}")
        cleaned = name.strip()
        if not cleaned:
            raise MapLibraryError("Territory name cannot be empty")
        item["name"] = cleaned
        text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
        return self.refresh_draft(replace(draft, map_yaml=text))

    def update_territory_display_name(
        self, draft: MapDraft, territory_id: TerritoryId, display_name: str
    ) -> MapDraft:
        document = load_yaml(draft.map_yaml)
        territories = document.get("territories", {})
        item = territories.get(str(territory_id))
        if not isinstance(item, dict):
            raise MapLibraryError(f"Unknown territory: {territory_id}")
        cleaned = display_name.strip()
        if not cleaned:
            raise MapLibraryError("Territory display name cannot be empty")
        item["display_name"] = cleaned
        text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
        return self.refresh_draft(replace(draft, map_yaml=text))

    def update_label_font_sizes(
        self, draft: MapDraft, territory_size: float, coast_size: float
    ) -> MapDraft:
        if not 5 <= territory_size <= 24 or not 5 <= coast_size <= 24:
            raise MapLibraryError("Label font sizes must be between 5 and 24")
        document = load_yaml(draft.map_yaml)
        presentation = document.setdefault("presentation", {})
        if not isinstance(presentation, dict):
            raise MapLibraryError("presentation must be a mapping")
        presentation["territory_label_font_size"] = round(territory_size, 1)
        presentation["coast_label_font_size"] = round(coast_size, 1)
        text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
        return self.refresh_draft(replace(draft, map_yaml=text))

    def update_map_colours(
        self,
        draft: MapDraft,
        label_colour: str,
        inaccessible_colour: str,
        sea_colour: str,
        unclaimed_colour: str,
    ) -> MapDraft:
        colours = (label_colour, inaccessible_colour, sea_colour, unclaimed_colour)
        if not all(re.fullmatch(r"#[0-9a-fA-F]{6}", colour) for colour in colours):
            raise MapLibraryError("Map colours must use #RRGGBB notation")
        document = load_yaml(draft.map_yaml)
        presentation = document.setdefault("presentation", {})
        if not isinstance(presentation, dict):
            raise MapLibraryError("presentation must be a mapping")
        presentation["label_colour"] = label_colour.lower()
        presentation["inaccessible_region_colour"] = inaccessible_colour.lower()
        presentation["sea_colour"] = sea_colour.lower()
        presentation["unclaimed_region_colour"] = unclaimed_colour.lower()
        text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
        return self.refresh_draft(replace(draft, map_yaml=text))

    def validate_starting_setup(
        self, map_definition: MapDefinition, starting_setup: StartingSetup
    ) -> MapValidation:
        issues: list[LocatedIssue] = []
        territories = {item.id: item for item in map_definition.territories}
        powers = {item.id for item in map_definition.powers}
        occupied: set[TerritoryId] = set()
        if starting_setup.phase_id.year < 1:
            issues.append(
                LocatedIssue(
                    Issue("start.invalid_year", "Year must be positive", IssueSeverity.ERROR),
                    IssueLocation("start.year"),
                )
            )
        if starting_setup.phase_id.season not in Season:
            issues.append(
                LocatedIssue(
                    Issue("start.invalid_season", "Unknown starting season", IssueSeverity.ERROR),
                    IssueLocation("start.season"),
                )
            )
        for unit in starting_setup.state.units:
            if unit.power_id not in powers or unit.location.territory_id not in territories:
                issues.append(
                    LocatedIssue(
                        Issue(
                            "start.invalid_unit",
                            "Starting unit references unknown map data",
                            IssueSeverity.ERROR,
                        ),
                        IssueLocation("start.units"),
                    )
                )
            if unit.location.territory_id in occupied:
                issues.append(
                    LocatedIssue(
                        Issue(
                            "start.duplicate_occupancy",
                            "Two units occupy one territory",
                            IssueSeverity.ERROR,
                        ),
                        IssueLocation("start.units", str(unit.location.territory_id)),
                    )
                )
            occupied.add(unit.location.territory_id)
        return MapValidation(tuple(issues))

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
