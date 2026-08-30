"""Order processor coordinating syntax and authoritative rule validation."""

from __future__ import annotations

from diplomacy_app.domain.models import (
    Issue,
    IssueSeverity,
    MapDefinition,
    OrderCandidate,
    OrderSubmission,
    PhaseSnapshot,
    PowerId,
    RuleValidation,
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
            map_definition,
            phase.phase_id,
            phase.resolution_state or phase.state,
            power_id,
            candidates,
        )
        by_line = {validation.source_line: validation for validation in validations}
        lines = tuple(
            SubmissionLine(candidate, by_line.get(candidate.source.number))
            for candidate in candidates
        )
        return OrderSubmission(power_id, raw_text, lines, False)

    def revalidate_submission(
        self,
        map_definition: MapDefinition,
        phase: PhaseSnapshot,
        submission: OrderSubmission,
    ) -> OrderSubmission:
        """Reparse saved text after a private game-map change.

        :param map_definition: Newly saved private map definition.
        :param phase: Stored phase whose state provides validation context.
        :param submission: Existing source-preserving order submission.
        :return: Reparsed submission retaining its finalisation state.
        """
        try:
            prepared = self.prepare_submission(
                map_definition,
                phase,
                submission.power_id,
                submission.raw_text,
            )
        except Exception as exc:
            candidates = self.interpret(
                map_definition,
                submission.power_id,
                submission.raw_text,
            )
            issue = Issue(
                "order.map_changed",
                f"Could not validate against the edited game map: {exc}",
                IssueSeverity.ERROR,
            )
            prepared = OrderSubmission(
                submission.power_id,
                submission.raw_text,
                tuple(
                    SubmissionLine(
                        candidate,
                        RuleValidation(candidate.source.number, False, (issue,), None)
                        if candidate.order is not None
                        else None,
                    )
                    for candidate in candidates
                ),
                False,
            )
        return OrderSubmission(
            prepared.power_id,
            prepared.raw_text,
            prepared.lines,
            submission.is_final,
        )
