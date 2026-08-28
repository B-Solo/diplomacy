"""Toolkit-independent conversion for structured map setup fields."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType

from diplomacy_app.domain.models import (
    CoastId,
    GameState,
    Location,
    MapDraft,
    PhaseId,
    PowerDefinition,
    PowerId,
    Season,
    StartingSetup,
    TerritoryId,
    UnitPosition,
    UnitType,
)

_POWER_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class PowerSetupRow:
    """Editable text fields representing one configured power."""

    power_id: str
    name: str
    colour: str
    home_centres: str
    starting_centres: str
    starting_territories: str
    initial_units: str


def _joined(values) -> str:
    """Return comma-separated stable identifiers for an error message.

    :param values: Iterable of identifier-like values.
    :return: Deterministically ordered comma-separated text.
    """
    return ", ".join(sorted(str(value) for value in values))


def _territory_ids(text: str) -> frozenset[TerritoryId]:
    """Parse comma-separated territory identifiers.

    :param text: Comma-separated stable territory IDs.
    :return: Parsed territory identifier set.
    """
    return frozenset(TerritoryId(value.strip()) for value in text.split(",") if value.strip())


def _location(text: str) -> Location:
    """Parse a territory or territory/coast table value.

    :param text: Stable authored location text.
    :return: Parsed application location.
    :raises ValueError: If the location is blank.
    """
    territory, separator, coast = text.strip().partition("/")
    if not territory:
        raise ValueError("Unit location cannot be blank")
    return Location(TerritoryId(territory), CoastId(coast) if separator and coast else None)


def _units(row: PowerSetupRow, power_id: PowerId) -> tuple[UnitPosition, ...]:
    """Parse one power's compact initial-unit field.

    :param row: Structured power row.
    :param power_id: Owning power identifier.
    :return: Parsed starting unit positions.
    :raises ValueError: If an entry does not use army/fleet notation.
    """
    units: list[UnitPosition] = []
    for entry in row.initial_units.split(","):
        entry = entry.strip()
        if not entry:
            continue
        unit_name, separator, location = entry.partition(" ")
        if not separator or unit_name.casefold() not in {"a", "army", "f", "fleet"}:
            raise ValueError(f"Invalid unit “{entry}”; use A territory or F territory/coast")
        unit_type = UnitType.ARMY if unit_name.casefold() in {"a", "army"} else UnitType.FLEET
        units.append(UnitPosition(power_id, unit_type, _location(location)))
    return tuple(units)


def build_setup(
    draft: MapDraft,
    year: int,
    season: Season,
    rows: tuple[PowerSetupRow, ...],
) -> tuple[tuple[PowerDefinition, ...], StartingSetup]:
    """Validate structured fields and construct complete setup contracts.

    :param draft: Map draft supplying known territories and retained retreat state.
    :param year: Positive starting year.
    :param season: Starting Diplomacy season.
    :param rows: Complete ordered power form.
    :return: Power definitions and complete starting setup ready for YAML mutation.
    :raises ValueError: If fields conflict or reference unknown map values.
    """
    powers: list[PowerDefinition] = []
    units: list[UnitPosition] = []
    controllers: dict[TerritoryId, PowerId | None] = {
        territory.id: None for territory in draft.territories
    }
    owners: dict[TerritoryId, PowerId | None] = {
        territory.id: None for territory in draft.territories if territory.is_supply_centre
    }
    known_territories = set(controllers)
    seen_powers: set[PowerId] = set()
    for row in rows:
        power_id = PowerId(row.power_id.strip())
        if not _POWER_ID.fullmatch(str(power_id)):
            raise ValueError(f"Invalid power ID: {power_id or '(blank)'}")
        if power_id in seen_powers:
            raise ValueError(f"Duplicate power ID: {power_id}")
        seen_powers.add(power_id)
        name = row.name.strip()
        colour = row.colour.strip().lower()
        if not name:
            raise ValueError(f"Power {power_id} requires a name")
        if not re.fullmatch(r"#[0-9a-f]{6}", colour):
            raise ValueError(f"Power {power_id} colour must use #RRGGBB notation")
        home = _territory_ids(row.home_centres)
        starting_centres = _territory_ids(row.starting_centres)
        starting_territories = _territory_ids(row.starting_territories)
        referenced = home | starting_centres | starting_territories
        unknown = referenced - known_territories
        if unknown:
            raise ValueError(f"Power {power_id} references unknown territories: {_joined(unknown)}")
        powers.append(PowerDefinition(power_id, name, colour, home))
        for territory in starting_centres:
            if owners.get(territory) is not None:
                raise ValueError(f"Starting supply centre {territory} has two owners")
            if territory not in owners:
                raise ValueError(f"{territory} is not a supply centre")
            owners[territory] = power_id
        for territory in starting_territories:
            if controllers[territory] is not None:
                raise ValueError(f"Starting territory {territory} has two controllers")
            controllers[territory] = power_id
        units.extend(_units(row, power_id))
    occupied: set[TerritoryId] = set()
    for unit in units:
        if unit.location.territory_id not in known_territories:
            raise ValueError(f"Unit references unknown territory: {unit.location.territory_id}")
        if unit.location.territory_id in occupied:
            raise ValueError(f"Two units occupy {unit.location.territory_id}")
        occupied.add(unit.location.territory_id)
    retained_dislodged = tuple(
        value
        for value in draft.default_starting_setup.state.dislodged_units
        if value.unit.power_id in seen_powers
    )
    setup = StartingSetup(
        PhaseId(year, season),
        GameState(
            tuple(units),
            retained_dislodged,
            MappingProxyType(controllers),
            MappingProxyType(owners),
        ),
    )
    return tuple(powers), setup
