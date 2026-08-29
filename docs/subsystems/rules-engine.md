# Rules Engine

## Responsibility

The Rules Engine is authoritative for phase requirements, legal orders, effective-order completion, adjudication and phase progression.
Its standard implementation isolates the bundled `diplomacy` package behind application-owned contracts.

## External API

The subsystem provides `RulesEngine` from [Subsystem API Contracts](../api-contracts.md).
`describe_phase` identifies legal decision makers, `validate` evaluates recognised candidates, `effective_orders` completes the phase order set and `adjudicate` returns an inert next-state proposal.

## Implementation Notes

The standard adapter reconstructs package state from the supplied immutable snapshot for each operation instead of retaining a second authoritative game instance.
This makes calls deterministic, avoids hidden state between validation and adjudication and permits independent adapter tests.

Validation submits recognised candidates in source order to a strict isolated game and translates the errors added by each attempt.
Validation also rejects order kinds that do not belong to the phase, while preserving the phase-specific default for the invalid candidate.
Adjudication enables `NO_CHECK` so recognised invalid movement orders remain recorded with `VOID`, keeps all five phase types in the history and carries post-movement state into the following retreat phase without displaying the movement as complete.
Effective-order completion follows standard phase behaviour: movement orders hold, retreat orders disband, unused builds waive and missing disbands are selected automatically.

The adapter translates map topology, split coasts, units, ownership and orders into package values, then maps package results back to stable application codes.
Retreat-state translation preserves dislodged units and the legal destinations calculated by the package.
Submission invalidity remains separate from adjudication outcomes such as `VOID`, bounce, cut or dislodgement.
Synthesised phase-default orders do not acquire fabricated source lines.

Alternative engines are registered by `engine_id` and implement the same protocol.

## Modules

- `registry` resolves a configured `engine_id` to a `RulesEngine` factory and rejects unknown engines while opening a game.
- `standard_engine` implements the public protocol and coordinates each isolated package invocation.
- `map_adapter` translates powers, provinces, coasts, canals and unit-specific adjacency into package map data.
- `state_adapter` constructs package phase state and converts resulting state back to application values.
- `order_adapter` translates typed candidates, completes invalid or omitted orders with phase-specific defaults, and maps package orders in both directions.
- `result_adapter` converts package result markers into stable application outcome codes.

Adapters fail with contextual `RulesEngineError` values when the package cannot represent a validated map or state.
Package objects remain local to a single public call.

## Dependencies

- Vendored `diplomacy` 1.1.2 at the pinned upstream commit recorded in [Technology Decisions](../technology-decisions.md).
- Shared map, phase and order contracts.
