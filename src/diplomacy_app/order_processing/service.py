"""Order processor coordinating syntax and authoritative rule validation."""

from __future__ import annotations

from diplomacy_app.domain.models import (
    MapDefinition,
    OrderCandidate,
    OrderSubmission,
    PhaseSnapshot,
    PowerId,
    SubmissionLine,
)
from diplomacy_app.order_processing.parser import parse_orders
from diplomacy_app.rules_engine.standard_engine import StandardRulesEngine


class OrderProcessor:
    def __init__(self, rules_engine: StandardRulesEngine) -> None:
        self.rules_engine = rules_engine

    def interpret(
        self, map_definition: MapDefinition, power_id: PowerId, raw_text: str
    ) -> tuple[OrderCandidate, ...]:
        return parse_orders(map_definition, power_id, raw_text)

    def prepare_submission(
        self,
        map_definition: MapDefinition,
        phase: PhaseSnapshot,
        power_id: PowerId,
        raw_text: str,
    ) -> OrderSubmission:
        candidates = self.interpret(map_definition, power_id, raw_text)
        validations = self.rules_engine.validate(
            map_definition, phase.phase_id, phase.state, power_id, candidates
        )
        by_line = {validation.source_line: validation for validation in validations}
        lines = tuple(
            SubmissionLine(candidate, by_line.get(candidate.source.number))
            for candidate in candidates
        )
        return OrderSubmission(power_id, raw_text, lines, False)
