# Application Coordinator

## Responsibility

The Application Coordinator implements user-level use cases and is the composition root for subsystem implementations.
It owns active session selection while repositories remain authoritative for persisted state.

## External API

The subsystem provides `ApplicationService` from [Subsystem API Contracts](../api-contracts.md).
It consumes `GameRepository`, `MapLibrary`, `OrderProcessor`, `RulesEngine`, `VisibilityProjector` and `MapRenderer`.

## Implementation Notes

Each mutation begins from a freshly loaded revision and commits through the Game Repository.
Revision conflicts are returned to the UI with a refreshed snapshot; mutations are not replayed implicitly because the user's input may need reconsideration.

The coordinator selects a Rules Engine implementation from `MapDefinition.rules_engine_id` and injects it into Order Processing.
It performs confirmation policy, session transitions and subsystem sequencing while keeping rule decisions and file formats out of its implementation.
For game creation, it obtains the configured map's default `StartingSetup`, submits any game-specific changes to Map Library validation and passes only validated setup to the Game Repository.

## Modules

- `service` implements `ApplicationService` and one method per user-level operation.
- `session` holds the selected game, phase and perspective and creates complete `SessionView` snapshots.
- `composition` constructs subsystem implementations, the rules-engine registry and the application service at startup.
- `errors` converts subsystem failures into the small set of application failures the UI can present.

`service` reloads authoritative snapshots at each mutation boundary and updates `session` only after a successful commit.
Read-only map composition may reuse an already loaded immutable phase snapshot when its revision still matches the session.

## Dependencies

- Every domain and persistence protocol defined by the subsystem contract.
- A rules-engine registry configured by the application entry point.
