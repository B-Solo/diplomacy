"""Reconstruct and extract bundled-engine state snapshots."""

from __future__ import annotations

from types import MappingProxyType

from diplomacy.engine.game import Game

from diplomacy_app.domain.errors import RulesEngineError
from diplomacy_app.domain.models import (
    DislodgedUnit,
    GameState,
    Location,
    MapDefinition,
    PhaseId,
    PowerId,
    Season,
    TerritoryId,
    UnitPosition,
    UnitType,
)
from diplomacy_app.rules_engine.map_adapter import (
    abbreviation_indexes,
    engine_abbreviations,
    engine_map_path,
    engine_power,
)


def phase_to_engine(value: PhaseId) -> str:
    if value.season is Season.SPRING:
        return f"S{value.year}M"
    if value.season is Season.SUMMER:
        return f"S{value.year}R"
    if value.season is Season.FALL:
        return f"F{value.year}M"
    if value.season is Season.WINTER:
        return f"F{value.year}R"
    return f"W{value.year}A"


def phase_from_engine(value: str) -> PhaseId:
    if value in {"COMPLETED", "FORMING"}:
        raise RulesEngineError(f"Game entered terminal engine phase: {value}")
    season_code, year, phase_type = value[0], int(value[1:5]), value[-1]
    if phase_type == "A":
        season = Season.YEAR_END
    elif season_code == "S" and phase_type == "M":
        season = Season.SPRING
    elif season_code == "S":
        season = Season.SUMMER
    elif phase_type == "M":
        season = Season.FALL
    else:
        season = Season.WINTER
    return PhaseId(year, season)


def _unit_text(unit: UnitPosition, names: dict[Location, str]) -> str:
    return f"{'A' if unit.unit_type is UnitType.ARMY else 'F'} {names[unit.location]}"


def make_game(map_definition: MapDefinition, phase_id: PhaseId, state: GameState) -> Game:
    try:
        path = engine_map_path(map_definition)
        game = Game(map_name=str(path), rules=[])
        if game.map.error:
            raise RulesEngineError(
                "Compiled map was rejected: " + "; ".join(map(str, game.map.error))
            )
        game.set_current_phase(phase_to_engine(phase_id))
        game.clear_units()
        game.clear_centers()
        _, names = abbreviation_indexes(map_definition)
        codes = engine_abbreviations(map_definition)
        for power in map_definition.powers:
            active = [_unit_text(unit, names) for unit in state.units if unit.power_id == power.id]
            dislodged_units = [
                "*" + _unit_text(item.unit, names)
                for item in state.dislodged_units
                if item.unit.power_id == power.id
            ]
            game.set_units(engine_power(power.id), active + dislodged_units, reset=True)
            centers = [
                codes[territory_id]
                for territory_id, owner in state.supply_centre_owners.items()
                if owner == power.id
            ]
            game.set_centers(engine_power(power.id), centers, reset=True)
            engine_instance = game.get_power(engine_power(power.id))
            engine_instance.influence = [
                codes[territory_id]
                for territory_id, controller in state.territory_controllers.items()
                if controller == power.id
            ]
        for dislodged in state.dislodged_units:
            power = game.get_power(engine_power(dislodged.unit.power_id))
            unit = _unit_text(dislodged.unit, names)
            power.retreats[unit] = [names[option] for option in dislodged.retreat_options]
        game.error = []
        game.rebuild_hash()
        game.build_caches()
        return game
    except RulesEngineError:
        raise
    except Exception as exc:
        raise RulesEngineError(f"Could not reconstruct rules-engine state: {exc}") from exc


def state_from_game(map_definition: MapDefinition, game: Game) -> GameState:
    forward, _ = abbreviation_indexes(map_definition)
    power_ids = {engine_power(power.id): power.id for power in map_definition.powers}
    units: list[UnitPosition] = []
    dislodged: list[DislodgedUnit] = []
    controllers: dict[TerritoryId, PowerId | None] = {
        item.id: None for item in map_definition.territories
    }
    owners: dict[TerritoryId, PowerId | None] = {
        item.id: None for item in map_definition.territories if item.is_supply_centre
    }

    def parse_unit(power_id: PowerId, value: str) -> UnitPosition:
        kind, abbreviation = value.split()[:2]
        location = forward[abbreviation.upper()]
        return UnitPosition(power_id, UnitType.ARMY if kind == "A" else UnitType.FLEET, location)

    for engine_name, power_id in power_ids.items():
        power = game.get_power(engine_name)
        units.extend(parse_unit(power_id, value) for value in power.units)
        for unit, options in power.retreats.items():
            dislodged.append(
                DislodgedUnit(
                    parse_unit(power_id, unit), tuple(forward[value.upper()] for value in options)
                )
            )
        for value in power.influence:
            location = forward.get(value.upper())
            if location:
                controllers[location.territory_id] = power_id
        for value in power.centers:
            location = forward.get(value.upper())
            if location:
                owners[location.territory_id] = power_id
    return GameState(
        tuple(units), tuple(dislodged), MappingProxyType(controllers), MappingProxyType(owners)
    )
