from __future__ import annotations

from types import MappingProxyType

from diplomacy.engine.map import Map

from diplomacy_app.domain.models import (
    GameId,
    GameState,
    Location,
    PhaseId,
    PhaseSnapshot,
    Revision,
    Season,
    UnitPosition,
    UnitType,
)
from diplomacy_app.order_processing import OrderProcessor
from diplomacy_app.rules_engine import StandardRulesEngine
from diplomacy_app.rules_engine.map_adapter import engine_map_path


def empty_phase(england):
    setup = england.default_starting_setup
    return PhaseSnapshot(
        GameId("test"),
        setup.phase_id,
        setup.state,
        MappingProxyType({}),
        (),
        Revision("test"),
    )


def test_generated_engine_map_is_valid(england):
    engine_map = Map(str(engine_map_path(england)))
    assert engine_map.error == []


def test_parser_accepts_names_abbreviations_and_reports_duplicates(england):
    engine = StandardRulesEngine()
    processor = OrderProcessor(engine)
    phase = empty_phase(england)
    power = england.powers[0]
    submission = processor.prepare_submission(
        england,
        phase,
        power.id,
        "A Cheshire H\nA Merseyside - Greater Manchester\nF Iom - Douglas Bay",
    )
    assert [line.candidate.canonical_text for line in submission.lines] == [
        "A Che H",
        "A Mer - Gma",
        "F Iom - DBY",
    ]
    assert all(line.validation and line.validation.is_valid for line in submission.lines)

    up_north = next(power for power in england.powers if power.name == "Up North")
    multiword_moves = processor.interpret(
        england,
        up_north.id,
        "F Tyne & Wear -> North Sea\nF Tyne & Wear - > North Sea",
    )
    assert [candidate.canonical_text for candidate in multiword_moves] == [
        "F Tyn - NTH",
        "F Tyn - NTH",
    ]
    support = processor.interpret(england, up_north.id, "F TYN S A DUR - CLE")
    assert [candidate.canonical_text for candidate in support] == ["F Tyn S A Dur - Cle"]
    phase_examples = processor.interpret(
        england,
        power.id,
        "A Cheshire R Shropshire\nA Cheshire B\nA Cheshire D\nWaive",
    )
    assert [candidate.canonical_text for candidate in phase_examples] == [
        "A Che R Shr",
        "A Che B",
        "A Che D",
        "Waive",
    ]

    duplicate = processor.prepare_submission(
        england, phase, power.id, "A Cheshire H\nA Cheshire - Shropshire"
    )
    assert all(line.validation and not line.validation.is_valid for line in duplicate.lines)
    assert all(line.validation.issues[0].code == "order.duplicate_unit" for line in duplicate.lines)


def test_empty_retreat_is_still_a_reached_phase(england):
    engine = StandardRulesEngine()
    phase = empty_phase(england)
    effective = engine.effective_orders(england, phase)
    assert len(effective) == len(phase.state.units)
    proposal = engine.adjudicate(england, phase)
    assert proposal.next_phase.label == "Summer 2000"
    assert proposal.next_state == phase.state
    assert proposal.next_resolution_state is not None
    assert len(proposal.next_resolution_state.units) == len(phase.state.units)
    assert len(proposal.results) == len(phase.state.units)


def test_empty_phases_are_retained_through_year_end(england):
    engine = StandardRulesEngine()
    phase = empty_phase(england)
    expected = (
        PhaseId(2000, Season.SUMMER),
        PhaseId(2000, Season.FALL),
        PhaseId(2000, Season.WINTER),
        PhaseId(2000, Season.YEAR_END),
        PhaseId(2001, Season.SPRING),
    )
    for expected_phase in expected:
        proposal = engine.adjudicate(england, phase)
        assert proposal.next_phase == expected_phase
        phase = PhaseSnapshot(
            phase.game_id,
            proposal.next_phase,
            proposal.next_state,
            MappingProxyType({}),
            (),
            phase.revision,
            proposal.next_resolution_state,
        )


def test_movement_waits_for_retreat_phase_to_complete(england):
    engine = StandardRulesEngine()
    processor = OrderProcessor(engine)
    power = england.powers[0]
    phase = empty_phase(england)
    submission = processor.prepare_submission(england, phase, power.id, "A Cheshire - Shropshire")
    spring = PhaseSnapshot(
        phase.game_id,
        phase.phase_id,
        phase.state,
        MappingProxyType({power.id: submission}),
        (),
        phase.revision,
    )

    summer_proposal = engine.adjudicate(england, spring)

    assert summer_proposal.next_phase == PhaseId(2000, Season.SUMMER)
    assert summer_proposal.next_state == spring.state
    assert summer_proposal.next_resolution_state is not None
    assert any(
        unit.location == Location("shropshire")
        for unit in summer_proposal.next_resolution_state.units
    )
    assert all(unit.location != Location("shropshire") for unit in summer_proposal.next_state.units)

    summer = PhaseSnapshot(
        spring.game_id,
        summer_proposal.next_phase,
        summer_proposal.next_state,
        MappingProxyType({}),
        (),
        spring.revision,
        summer_proposal.next_resolution_state,
    )
    fall_proposal = engine.adjudicate(england, summer)

    assert fall_proposal.next_phase == PhaseId(2000, Season.FALL)
    assert fall_proposal.next_state == summer.resolution_state
    assert fall_proposal.next_resolution_state is None


def test_retreat_orders_use_pending_movement_state(england):
    engine = StandardRulesEngine()
    processor = OrderProcessor(engine)
    merseyside, up_north = england.powers[:2]
    state = GameState(
        (
            UnitPosition(merseyside.id, UnitType.ARMY, Location("cheshire")),
            UnitPosition(merseyside.id, UnitType.ARMY, Location("staffordshire")),
            UnitPosition(up_north.id, UnitType.ARMY, Location("derbyshire-and-nottinghamshire")),
        ),
        (),
        MappingProxyType({territory.id: None for territory in england.territories}),
        MappingProxyType(
            {territory.id: None for territory in england.territories if territory.is_supply_centre}
        ),
    )
    spring = PhaseSnapshot(
        GameId("retreat"),
        PhaseId(2000, Season.SPRING),
        state,
        MappingProxyType({}),
        (),
        Revision("retreat"),
    )
    merseyside_orders = processor.prepare_submission(
        england,
        spring,
        merseyside.id,
        "A Cheshire - Derbyshire & Nottinghamshire\n"
        "A Staffordshire S A Cheshire - Derbyshire & Nottinghamshire",
    )
    up_north_orders = processor.prepare_submission(
        england, spring, up_north.id, "A Derbyshire & Nottinghamshire H"
    )
    spring = PhaseSnapshot(
        spring.game_id,
        spring.phase_id,
        state,
        MappingProxyType({merseyside.id: merseyside_orders, up_north.id: up_north_orders}),
        (),
        spring.revision,
    )
    summer_proposal = engine.adjudicate(england, spring)
    assert summer_proposal.next_resolution_state is not None
    summer = PhaseSnapshot(
        spring.game_id,
        summer_proposal.next_phase,
        spring.state,
        MappingProxyType({}),
        (),
        spring.revision,
        summer_proposal.next_resolution_state,
    )

    invalid = processor.prepare_submission(
        england, summer, up_north.id, "A Derbyshire & Nottinghamshire - Humberside"
    )
    retreat = processor.prepare_submission(
        england, summer, up_north.id, "A Derbyshire & Nottinghamshire R Humberside"
    )
    assert invalid.lines[0].validation is not None
    assert not invalid.lines[0].validation.is_valid
    assert retreat.lines[0].validation is not None
    assert retreat.lines[0].validation.is_valid

    summer = PhaseSnapshot(
        summer.game_id,
        summer.phase_id,
        summer.state,
        MappingProxyType({up_north.id: retreat}),
        (),
        summer.revision,
        summer.resolution_state,
    )
    fall_proposal = engine.adjudicate(england, summer)

    assert fall_proposal.next_state.dislodged_units == ()
    assert any(unit.location == Location("humberside") for unit in fall_proposal.next_state.units)
    assert len({unit.location.territory_id for unit in fall_proposal.next_state.units}) == len(
        fall_proposal.next_state.units
    )


def test_year_end_rejects_movement_orders(england):
    engine = StandardRulesEngine()
    processor = OrderProcessor(engine)
    phase = PhaseSnapshot(
        GameId("year-end"),
        PhaseId(2000, Season.YEAR_END),
        england.default_starting_setup.state,
        MappingProxyType({}),
        (),
        Revision("year-end"),
    )
    validation = (
        processor.prepare_submission(england, phase, england.powers[0].id, "A Cheshire H")
        .lines[0]
        .validation
    )
    assert validation is not None
    assert not validation.is_valid
    assert validation.issues[0].code == "order.wrong_phase"
