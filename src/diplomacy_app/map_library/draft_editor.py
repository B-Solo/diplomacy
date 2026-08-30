"""Pure authored-YAML mutations for reusable map drafts."""

from __future__ import annotations

import math
import re
from dataclasses import replace
from types import MappingProxyType
from typing import Any

import yaml

from diplomacy_app.domain.errors import MapLibraryError
from diplomacy_app.domain.models import (
    MapDraft,
    MapId,
    Point,
    PowerDefinition,
    StartingSetup,
    SvgElementRole,
    TerritoryId,
)
from diplomacy_app.map_library.map_codec import compile_map, load_yaml
from diplomacy_app.map_library.svg_importer import territory_geometries


def refresh_draft(draft: MapDraft) -> MapDraft:
    """Rebuild every derived draft value from its authored YAML.

    :param draft: Draft whose YAML is authoritative.
    :return: Draft containing freshly compiled domain values.
    """
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


def update_identity(draft: MapDraft, map_id: MapId, name: str) -> MapDraft:
    """Give a copied reusable map a new stable identity.

    :param draft: Authored map draft to copy.
    :param map_id: New lowercase stable map identifier.
    :param name: New user-facing map name.
    :return: Recompiled draft containing the new identity.
    :raises MapLibraryError: If either identity field is empty.
    """
    cleaned_id = str(map_id).strip()
    cleaned_name = name.strip()
    if not cleaned_id:
        raise MapLibraryError("Map ID cannot be empty")
    if not cleaned_name:
        raise MapLibraryError("Map name cannot be empty")
    document = load_yaml(draft.map_yaml)
    document["map_id"] = cleaned_id
    document["name"] = cleaned_name
    return _updated_yaml(draft, document)


def _updated_yaml(draft: MapDraft, document: dict[str, Any]) -> MapDraft:
    """Serialise one edited document and compile its derived values.

    :param draft: Source draft whose SVG and element roles remain authoritative.
    :param document: Complete edited authored YAML mapping.
    :return: Recompiled draft containing the document.
    """
    text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
    return refresh_draft(replace(draft, map_yaml=text))


def update_anchor(
    draft: MapDraft,
    territory_id: TerritoryId,
    anchor: str,
    point: Point,
    coast_id: str | None = None,
) -> MapDraft:
    """Update one ordinary or named-coast presentation anchor.

    :param draft: Authored map draft to update.
    :param territory_id: Territory containing the anchor.
    :param anchor: Authored anchor name.
    :param point: New source-SVG coordinate.
    :param coast_id: Optional named coast for fleet or coast-label anchors.
    :return: Recompiled draft containing the anchor.
    :raises MapLibraryError: If the territory is unknown.
    """
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
    return _updated_yaml(draft, document)


def update_coast_label_rotation(
    draft: MapDraft,
    territory_id: TerritoryId,
    coast_id: str,
    rotation: float,
) -> MapDraft:
    """Update one named-coast label rotation.

    :param draft: Authored map draft to update.
    :param territory_id: Split-coast territory.
    :param coast_id: Named coast within the territory.
    :param rotation: Clockwise label rotation in degrees.
    :return: Recompiled draft containing the rotation.
    :raises MapLibraryError: If the territory or coast is unknown.
    """
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
    return _updated_yaml(draft, document)


def update_element_role(draft: MapDraft, element_id: str, role: SvgElementRole) -> MapDraft:
    """Reclassify one identified SVG element during exceptional import correction.

    :param draft: Authored map draft to update.
    :param element_id: Existing SVG element identifier.
    :param role: New playable, impassable, or decorative role.
    :return: Recompiled draft containing the classification.
    """
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
    return refresh_draft(replace(draft, map_yaml=text, element_roles=MappingProxyType(roles)))


def update_territory_name(draft: MapDraft, territory_id: TerritoryId, name: str) -> MapDraft:
    """Update one canonical territory name.

    :param draft: Authored map draft to update.
    :param territory_id: Stable territory identifier.
    :param name: Canonical order-entry name.
    :return: Recompiled draft containing the name.
    :raises MapLibraryError: If the territory or name is invalid.
    """
    document = load_yaml(draft.map_yaml)
    territories = document.get("territories", {})
    item = territories.get(str(territory_id))
    if not isinstance(item, dict):
        raise MapLibraryError(f"Unknown territory: {territory_id}")
    cleaned = name.strip()
    if not cleaned:
        raise MapLibraryError("Territory name cannot be empty")
    item["name"] = cleaned
    return _updated_yaml(draft, document)


def update_territory_display_name(
    draft: MapDraft, territory_id: TerritoryId, display_name: str
) -> MapDraft:
    """Update one map-facing territory label.

    :param draft: Authored map draft to update.
    :param territory_id: Stable territory identifier.
    :param display_name: Potentially multiline map label.
    :return: Recompiled draft containing the display name.
    :raises MapLibraryError: If the territory or label is invalid.
    """
    document = load_yaml(draft.map_yaml)
    territories = document.get("territories", {})
    item = territories.get(str(territory_id))
    if not isinstance(item, dict):
        raise MapLibraryError(f"Unknown territory: {territory_id}")
    cleaned = display_name.strip()
    if not cleaned:
        raise MapLibraryError("Territory display name cannot be empty")
    item["display_name"] = cleaned
    return _updated_yaml(draft, document)


def update_territory_details(
    draft: MapDraft,
    territory_id: TerritoryId,
    name: str,
    display_name: str,
    abbreviation: str,
) -> MapDraft:
    """Update the user-facing names of one territory in one compilation.

    :param draft: Authored map draft to update.
    :param territory_id: Stable territory whose names should change.
    :param name: Canonical name accepted by order entry.
    :param display_name: Potentially multiline map label.
    :param abbreviation: Unique three-letter order abbreviation.
    :return: Recompiled draft containing the updated territory.
    :raises MapLibraryError: If the territory or supplied names are invalid.
    """
    cleaned_name = name.strip()
    cleaned_display_name = display_name.strip()
    cleaned_abbreviation = abbreviation.strip()
    if not cleaned_name:
        raise MapLibraryError("Territory name cannot be empty")
    if not cleaned_display_name:
        raise MapLibraryError("Territory display name cannot be empty")
    if not re.fullmatch(r"[A-Za-z]{3}", cleaned_abbreviation):
        raise MapLibraryError("Territory abbreviation must be exactly three ASCII letters")
    document = load_yaml(draft.map_yaml)
    territories = document.get("territories", {})
    item = territories.get(str(territory_id))
    if not isinstance(item, dict):
        raise MapLibraryError(f"Unknown territory: {territory_id}")
    item["name"] = cleaned_name
    item["display_name"] = cleaned_display_name
    item["abbreviation"] = cleaned_abbreviation
    return _updated_yaml(draft, document)


def update_setup(
    draft: MapDraft,
    powers: tuple[PowerDefinition, ...],
    starting_setup: StartingSetup,
) -> MapDraft:
    """Replace structured powers and starting state in authored YAML.

    :param draft: Authored map draft to update.
    :param powers: Complete ordered power definitions.
    :param starting_setup: Complete starting phase and state.
    :return: Recompiled draft containing the updated setup.
    """
    document = load_yaml(draft.map_yaml)
    document["start"] = {
        "year": starting_setup.phase_id.year,
        "season": starting_setup.phase_id.season.value,
    }
    state = starting_setup.state
    teams: dict[str, Any] = {}
    for power in powers:
        power_id = power.id
        item: dict[str, Any] = {
            "name": power.name,
            "colour": power.colour,
            "home_supply_centres": sorted(str(value) for value in power.home_supply_centres),
            "starting_supply_centres": [
                str(territory_id)
                for territory_id, owner in state.supply_centre_owners.items()
                if owner == power_id
            ],
            "starting_territories": [
                str(territory_id)
                for territory_id, controller in state.territory_controllers.items()
                if controller == power_id
            ],
            "initial_units": [
                {
                    "type": unit.unit_type.value,
                    "location": str(unit.location.territory_id)
                    + (f"/{unit.location.coast_id}" if unit.location.coast_id else ""),
                }
                for unit in state.units
                if unit.power_id == power_id
            ],
        }
        dislodged_units = [
            {
                "type": value.unit.unit_type.value,
                "location": str(value.unit.location.territory_id)
                + (f"/{value.unit.location.coast_id}" if value.unit.location.coast_id else ""),
                "retreat_options": [
                    str(location.territory_id)
                    + (f"/{location.coast_id}" if location.coast_id else "")
                    for location in value.retreat_options
                ],
            }
            for value in state.dislodged_units
            if value.unit.power_id == power_id
        ]
        if dislodged_units:
            item["initial_dislodged_units"] = dislodged_units
        teams[str(power_id)] = item
    document["teams"] = teams
    return _updated_yaml(draft, document)


def update_label_font_sizes(draft: MapDraft, territory_size: float, coast_size: float) -> MapDraft:
    """Update map-wide territory and coast label sizes.

    :param draft: Authored map draft to update.
    :param territory_size: Territory label point size.
    :param coast_size: Named-coast label point size.
    :return: Recompiled draft containing the sizes.
    :raises MapLibraryError: If either size is outside the supported range.
    """
    if not 5 <= territory_size <= 24 or not 5 <= coast_size <= 24:
        raise MapLibraryError("Label font sizes must be between 5 and 24")
    document = load_yaml(draft.map_yaml)
    presentation = document.setdefault("presentation", {})
    if not isinstance(presentation, dict):
        raise MapLibraryError("presentation must be a mapping")
    presentation["territory_label_font_size"] = round(territory_size, 1)
    presentation["coast_label_font_size"] = round(coast_size, 1)
    return _updated_yaml(draft, document)


def update_hold_offsets(draft: MapDraft, army_offset: Point, fleet_offset: Point) -> MapDraft:
    """Update map-wide hold-underline positions relative to their unit anchors.

    :param draft: Authored map draft to update.
    :param army_offset: Army underline offset in source-SVG coordinates.
    :param fleet_offset: Fleet underline offset in source-SVG coordinates.
    :return: Recompiled draft containing both offsets.
    :raises MapLibraryError: If an offset is non-finite or outside the editor range.
    """
    coordinates = (
        army_offset.x,
        army_offset.y,
        fleet_offset.x,
        fleet_offset.y,
    )
    if not all(math.isfinite(value) and -50 <= value <= 50 for value in coordinates):
        raise MapLibraryError("Hold underline offsets must be between -50 and 50")
    document = load_yaml(draft.map_yaml)
    presentation = document.setdefault("presentation", {})
    if not isinstance(presentation, dict):
        raise MapLibraryError("presentation must be a mapping")
    presentation["hold_underlines"] = {
        "army": [round(army_offset.x, 1), round(army_offset.y, 1)],
        "fleet": [round(fleet_offset.x, 1), round(fleet_offset.y, 1)],
    }
    return _updated_yaml(draft, document)


def update_map_colours(
    draft: MapDraft,
    label_colour: str,
    inaccessible_colour: str,
    sea_colour: str,
    unclaimed_colour: str,
) -> MapDraft:
    """Update every map-wide presentation colour.

    :param draft: Authored map draft to update.
    :param label_colour: Territory and coast label colour.
    :param inaccessible_colour: Base inaccessible-region stripe colour.
    :param sea_colour: Uncontrolled sea fill colour.
    :param unclaimed_colour: Uncontrolled land fill colour.
    :return: Recompiled draft containing the colours.
    :raises MapLibraryError: If any value is not #RRGGBB notation.
    """
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
    return _updated_yaml(draft, document)
