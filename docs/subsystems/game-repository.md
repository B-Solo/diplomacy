# Game Repository

## Responsibility

The Game Repository owns all reads and writes beneath active game folders and maps stored files to immutable contract snapshots.
It also maintains the small application-owned record of recent and last-opened game locations.

## External API

The subsystem provides `GameRepository` from [Subsystem API Contracts](../api-contracts.md).
Its callers can discover, open and create games; load phases; save submissions and views; change finalisation; and commit adjudication proposals.

## Implementation Notes

Stored data is parsed into application contract values at the repository boundary and validated before being returned.
Unknown or malformed data produces `InvalidStoredData` with file and logical-location context.
Retreat-phase codecs preserve dislodged units and their legal destinations independently of active occupying units.
Game creation copies the configured map, materialises the validated game-specific setup into that private copy and writes its first phase state before exposing the game folder as complete.

Every write is staged beside its destination, flushed and then installed using recoverable renames.
Multi-file adjudication uses the redo manifest and recovery marker defined in [Storage Schema](../storage-schema.md), so reopening a game completes an interrupted commit deterministically.

The repository derives a `Revision` from authoritative file paths and content and checks it immediately before mutation.
This detects stale UI work and external file edits without exposing filesystem metadata to other subsystems.

## Modules

- `repository` implements `GameRepository` and coordinates codecs, revision checks and filesystem commits.
- `game_codec` maps game metadata, map snapshots and saved views between stored schemas and contract values.
- `phase_codec` maps state, submitted text, canonical orders, validation and results for one phase.
- `transaction` stages multi-file changes, records recovery intent and completes interrupted commits during open.
- `revision` derives and verifies repository generations without leaking file timestamps into contracts.
- `recent_games` owns the last-opened pointer and ordered recent-game catalogue outside self-contained game folders.

Codecs validate schema versions before constructing contract objects.
`transaction` is the only module permitted to replace committed files.

## Dependencies

- Local filesystem, Pydantic storage models, PyYAML and standard-library JSON.
- Shared contract values only; it does not depend on rules or rendering implementations.
