from __future__ import annotations

from types import MappingProxyType

from diplomacy.engine.map import Map

from diplomacy_app.domain.models import GameId, PhaseSnapshot, Revision
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

    duplicate = processor.prepare_submission(
        england, phase, power.id, "A Cheshire H\nA Cheshire - Shropshire"
    )
    assert all(line.validation and not line.validation.is_valid for line in duplicate.lines)
    assert all(line.validation.issues[0].code == "order.duplicate_unit" for line in duplicate.lines)


def test_default_orders_advance_without_skipping_empty_retreat(england):
    engine = StandardRulesEngine()
    phase = empty_phase(england)
    effective = engine.effective_orders(england, phase)
    assert len(effective) == len(phase.state.units)
    proposal = engine.adjudicate(england, phase)
    assert proposal.next_phase.label == "Summer 2000"
    assert len(proposal.next_state.units) == len(phase.state.units)
    assert len(proposal.results) == len(phase.state.units)
