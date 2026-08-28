"""Semantic validation for configured maps and game starting setups."""

from __future__ import annotations

import re

from diplomacy_app.domain.errors import MapLibraryError
from diplomacy_app.domain.models import (
    Issue,
    IssueLocation,
    IssueSeverity,
    LocatedIssue,
    MapDefinition,
    MapDraft,
    MapValidation,
    Season,
    StartingSetup,
    TerritoryId,
    TerritoryKind,
)
from diplomacy_app.map_library.map_codec import compile_map
from diplomacy_app.map_library.svg_importer import element_ids

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ABBREVIATION = re.compile(r"^[A-Za-z]{3}$")


def validate_map_draft(draft: MapDraft) -> MapValidation:
    """Validate a complete authored map draft.

    :param draft: Draft containing authored YAML and its sanitised SVG.
    :return: Every located semantic validation issue found in the draft.
    """
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


def validate_starting_setup(
    map_definition: MapDefinition, starting_setup: StartingSetup
) -> MapValidation:
    """Validate game-specific starting state against an immutable map.

    :param map_definition: Configured map that owns powers and territories.
    :param starting_setup: Game-specific phase and state to validate.
    :return: Every located semantic validation issue found in the setup.
    """
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
