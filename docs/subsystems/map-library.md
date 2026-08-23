# Map Library

## Responsibility

The Map Library imports, validates and stores reusable configured maps.
It owns map drafts and reusable-map files while active-game copies belong to the Game Repository.

## External API

The subsystem provides `MapLibrary` from [Subsystem API Contracts](../api-contracts.md).
Its callers can list and load maps, import SVG content, validate a draft and save a validated `MapDefinition`.

## Implementation Notes

Import first sanitises SVG content by removing scripts, event handlers and external resource references.
It indexes uniquely identified shapes, calculates initial interior anchors and generates adjacency candidates from shared geometry.
Every coastal province begins with one continuous coast; the authored map declares split coasts and local exceptional links or removals.

Geometry infers army movement across a shared land border and fleet movement across a shared navigable border between sea or coastal regions.
Declaring `split_coasts` suppresses ordinary inferred fleet connections for that province, after which its local additions assign neighbouring fleet locations to named coasts explicitly.
The saved effective topology is materialised as JSON so later geometry-library changes cannot alter an existing configured map implicitly.

Validation covers identifier uniqueness, abbreviation uniqueness, topology symmetry, unit-specific reachability, power starts, supply centres, anchor coverage and SVG references.
Issues use stable codes and point to the relevant map YAML field or source line.
The same validation components check a game-specific starting year, season, units, supply-centre ownership and territory control while treating configured powers, colours, home supply centres and topology as immutable.

Saving writes a complete reusable map folder atomically.
Default army and fleet assets are substituted when a draft omits either optional custom symbol.

## Modules

- `library` implements `MapLibrary` and coordinates import, validation and reusable-map storage.
- `svg_importer` sanitises SVG, inventories element identifiers and proposes playable, impassable and decorative classifications.
- `geometry` calculates shared-boundary adjacency candidates and initial interior anchors without claiming rule validity.
- `map_codec` parses the single authored map YAML, combines inferred geometry with local connection additions and removals, and emits the complete machine-managed map JSON.
- `validator` performs semantic and asset-reference checks and reports located issues with stable codes.
- `storage` reads and atomically writes complete reusable-map folders.
- `defaults` supplies the standard army and fleet assets when custom assets are absent.

The importer retains generated values in the draft so manual corrections survive repeated validation.
The map codec preserves user YAML text and gives generated JSON a stable ordering for readable diffs.

## Dependencies

- `defusedxml.ElementTree`, `svgelements` and Shapely.
- PyYAML and Pydantic storage models.
- Local reusable-map storage.
