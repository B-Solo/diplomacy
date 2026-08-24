# Storage Schema

## Purpose

This document defines the versioned filesystem layout and the user-editable map schemas.
Configured maps and game folders use the same map representation so a game remains self-contained.

## Format Convention

YAML contains authored configuration that the map wizard creates and the gamemaster may inspect or edit.
Normal play does not rewrite YAML.
JSON contains runtime state or materialised data maintained by the application and may be replaced during normal use.
SVG contains the supplied map and unit artwork.

## Application-Owned Storage

`platformdirs` selects the operating-system locations for application configuration and reusable maps.
Machine-managed `application.json` contains recent-game locations, the last-opened game location and application-level preferences.
Reusable maps live under the application data directory in `maps/<map-id>/`.

## Game Folder Layout

```text
<game>/
├── game.yaml
├── views.json
├── map/
│   ├── map.yaml
│   ├── map.svg
│   ├── army.svg
│   ├── fleet.svg
│   ├── _compiled-map.json
│   └── _engine.map
├── 1901/
│   ├── Spring/
│   │   ├── state.json
│   │   └── orders.json
│   ├── Summer/
│   │   ├── state.json
│   │   └── orders.json
│   ├── Fall/
│   │   ├── state.json
│   │   └── orders.json
│   ├── Winter/
│   │   ├── state.json
│   │   └── orders.json
│   └── YearEnd/
│       ├── state.json
│       └── orders.json
└── .transactions/
```

Only phase folders reached by the game exist.
Every reached phase has `state.json`; `orders.json` is created on the first order edit or when an empty phase is resolved.
The chronologically latest phase containing `state.json` is the current phase, whether or not its editable `orders.json` already exists.

The `map/` directory is a private snapshot of the configured map at game creation.
Changing a reusable map does not affect existing games, while a game-specific starting year, season, unit placement, supply-centre ownership or territory control is materialised only in its private snapshot before play begins.
Powers, colours, home supply centres and topology remain those of the reusable configured map.
During game creation, the repository writes the selected setup into the private `map/map.yaml`, recompiles that snapshot and creates the corresponding first `state.json`.
During play, the placement-only editor may transactionally replace presentation anchors and named-coast label rotations in the private `map/map.yaml` and `_compiled-map.json` without changing map identity or rules data.

`army.svg` and `fleet.svg` are materialised from application defaults when the configured map does not provide custom symbols.
`_compiled-map.json` and `_engine.map` are generated from the authored map and are never authoritative.

## Game Configuration

`game.yaml` contains static, human-readable game identity and configuration:

```yaml
schema_version: 1
game_id: northern-england-uni-friends
name: Northern England
fog_of_war:
  enabled: true
  adjacency_depth: 1
ui:
  explain_adjudication_outcomes: false
```

The reusable default starting phase belongs to `map/map.yaml`, avoiding two configuration fields for the same fact.
`views.json` is machine-managed and stores saved views because they change during normal use.
Saved-view bounds use source-SVG view-box coordinates in `x, y, width, height` order.

## Configured Map

`map/map.yaml` is the single authored description of a configured map.
Map-wide identity and starting defaults appear first, while territory-specific rules and presentation are grouped under their territory identifiers:

```yaml
schema_version: 1
map_id: england
name: England
rules_engine: standard
assets:
  map: map.svg
  army: army.svg
  fleet: fleet.svg

presentation:
  territory_label_font_size: 11.0
  coast_label_font_size: 9.0
  inaccessible_region_colour: "#777870"
  sea_colour: "#9ebbd2"
  unclaimed_region_colour: "#d0c9aa"

start:
  year: 1901
  season: spring

teams:
  red:
    name: Red
    colour: "#c9413a"
    home_supply_centres: [london]
    starting_supply_centres: [london]
    starting_territories: [london, kent]
    initial_units:
      - type: army
        location: london

territories:
  london:
    name: London
    display_name: London
    abbreviation: Lon
    kind: land
    svg_element: territory-london
    supply_centre: true
    anchors:
      label: [512.5, 488.0]
      army: [510.0, 505.0]
      fleet: [514.0, 507.0]
      supply_centre: [520.0, 490.0]

  north-sea:
    name: North Sea
    abbreviation: NTH
    kind: sea
    svg_element: territory-north-sea
    anchors:
      label: [620.0, 210.0]
      fleet: [625.0, 235.0]
    connection_overrides:
      add:
        - to: off-map-sea
          units: [fleet]

  canal-province:
    name: Canal Province
    abbreviation: Can
    kind: land
    svg_element: territory-canal-province
    anchors:
      label: [700.0, 350.0]
      army: [695.0, 370.0]
      fleet: [705.0, 370.0]
    connection_overrides:
      add:
        - to: canal-linked-sea
          units: [fleet]
      remove:
        - to: visually-touching-sea
          units: [fleet]

  example-split-coast:
    name: Example Split Coast
    display_name: |-
      Example Split
      Coast
    abbreviation: Esc
    kind: land
    svg_element: territory-example-split-coast
    anchors:
      label: [600.0, 140.0]
      abbreviation: [608.0, 136.0]
      army: [600.0, 150.0]
    split_coasts:
      north:
        fleet_anchor: [600.0, 120.0]
        label_anchor: [600.0, 102.0]
        label_rotation: 0
        add_connections: [north-sea]
      south:
        fleet_anchor: [605.0, 165.0]
        label_anchor: [605.0, 183.0]
        label_rotation: 0
        add_connections: [south-sea]

non_playable_elements:
  region-impassable: impassable
  map-decoration: decoration
```

Territory and team identifiers are lowercase stable slugs. A territory's canonical `name` is used by players and order entry, while its optional `display_name` controls map text and may contain explicit line breaks; omitting it displays the canonical name.
Abbreviations contain exactly three ASCII letters and are unique without regard to case.
Land abbreviations use initial-capital display form, and sea abbreviations use uppercase display form.
If `anchors.abbreviation` is omitted, it initially uses `anchors.label`; moving either label in Placement then stores its position independently.

Every playable territory references exactly one SVG element and owns its label, unit and optional supply-centre anchors.
Coordinates use source-SVG view-box coordinates.
Every territory has a label anchor, every land territory has an army anchor, every coastal location and sea has a fleet anchor, and every supply centre has a supply-centre anchor.
Every named split coast has its own visible label anchor and rotation.
Territory labels and named-coast labels each use one map-wide font size.
Inaccessible regions, seas and unclaimed land each use one map-wide presentation colour.

The importer derives ordinary bidirectional movement from SVG geometry, territory types and the default single-coast assumption.
Ordinary movement has no YAML entry.
`connection_overrides` contains only additions or removals, and each exception is written beneath exactly one of its endpoint territories.
An exception names the other endpoint and the affected `army` or `fleet` unit types.

`split_coasts` is omitted for inland provinces, seas and ordinary coastal provinces with one continuous coast.
Declaring split coasts suppresses inferred fleet connections for that province.
Each named coast therefore supplies its fleet anchor and exceptional neighbouring fleet locations directly.
Its optional `label_anchor` and `label_rotation` position the visible coast name; missing presentation values derive from the fleet anchor for compatibility with existing maps.

Team identifiers compile to Rules Engine powers.
`home_supply_centres` defines legal home build sites, while `starting_supply_centres` defines ownership at the beginning of the game.
`starting_territories` defines initial map colouring independently of supply-centre ownership.
Supply centres and land territories omitted by every team begin neutral and uncontrolled.
Unit types are `army` and `fleet`, and fleet locations use a named coast when the occupied province has split coasts.
Season values are `spring`, `summer`, `fall`, `winter` and `year_end`.
When a map starts in a retreat season, each team's optional `initial_dislodged_units` entries contain `type`, `location` and `retreat_options` fields.
That field is omitted for other starting seasons.

When map setup is saved, the Map Library materialises the complete validated `MapDefinition` in `_compiled-map.json` and records a digest of `map.yaml` and the SVG assets.
The compiled map is the representation loaded during play and remains stable across application upgrades.
Editing an authored source makes the compiled digest stale and requires map validation before recompilation.
The map editor visualises the complete effective topology over the map while keeping the authored connection exceptions local to their territories.

Validation covers unique identifiers and abbreviations, SVG references, required anchors, team starts and the complete effective topology.
Connection additions cannot duplicate inferred movement, removals must identify inferred movement, and duplicate bidirectional exceptions are rejected even when written under opposite endpoints.
Army connections use base land territories, while fleet connections use seas, ordinary coastal provinces or named split coasts.
Home and starting supply centres are actual supply centres, starting territories are land, initial active and dislodged units occupy legal distinct locations, retreat destinations are legal for the configured phase, and no starting possession belongs to two teams.

## Phase State

`state.json` is machine-managed and records the complete state at the beginning of its phase.
It contains `schema_version`, the phase identifier, active units, dislodged units, legal retreat destinations, territory controllers and supply-centre owners using stable map identifiers.
Dislodged units and their retreat destinations are present only in retreat-phase state.

`orders.json` is machine-managed and records each power's original text, canonical candidates, parser issues, rule validation, final flag, effective orders and adjudication results.
The file preserves unrecognised lines and distinguishes submission invalidity from the later `VOID` outcome.
Effective orders record phase-specific defaults: movement holds, retreat disbands, waived builds and automatically selected disbands.

JSON arrays preserve source-line and rendering order.
JSON objects with identifiers as keys are emitted in identifier order for readable diffs.

## Recoverable Phase Advancement

Advancing a phase must make the completed `orders.json` and the next `state.json` visible as one logical change.
A normal filesystem cannot atomically replace files in several directories, so the repository uses a small redo transaction:

1. It creates `.transactions/<transaction-id>/` on the same filesystem as the game folder.
2. It writes every new file into that directory together with `manifest.json`, containing target paths and SHA-256 digests.
3. It flushes the staged files and transaction directory.
4. It atomically installs `.transaction.json` at the game root, making the prepared transaction recoverable.
5. It installs each target with `os.replace`, checking whether an already-installed target has the manifest digest.
6. It installs the next phase's `state.json` last, flushes affected directories and removes the marker and staging directory.

Opening a game checks for the marker before reading any snapshots.
If a marker exists, the repository idempotently installs every missing target from the staged transaction and verifies every digest before removing the marker.
The operation therefore completes after a crash instead of exposing a half-advanced game or attempting to reverse adjudication.

Ordinary order edits, finalisation changes and saved-view changes affect one authoritative JSON file and use a temporary sibling followed by `os.replace`.
The repository computes `Revision` from the paths and bytes of the authoritative files involved in a snapshot, detecting both application changes and external edits.

## Schema Evolution

Every YAML and JSON document begins with an integer `schema_version`.
Readers validate the stated version exactly, and explicit migrations create a backup before rewriting an older schema.
Derived files and transaction manifests have separate internal versions and never drive migration of authoritative data.
