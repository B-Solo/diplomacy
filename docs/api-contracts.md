# Subsystem API Contracts

## Purpose

This document defines the typed in-process contracts between the subsystems in [Functional Structure](functional-structure.md).
The contracts use application-owned values so each subsystem can be implemented and tested independently.

The definitions below are normative Python-shaped sketches.
They fix ownership, inputs, outputs and failure semantics while leaving helper methods and internal representations to the subsystem designs.
The sketches assume postponed evaluation of annotations.

## Contract Conventions

### Values

Boundary values are deeply immutable snapshots.
Collections exposed by a contract are tuples, frozen sets or immutable mappings.
A subsystem creates a new value when information changes.

Identifiers are distinct string-backed value types:

```python
GameId = NewType("GameId", str)
MapId = NewType("MapId", str)
PowerId = NewType("PowerId", str)
TerritoryId = NewType("TerritoryId", str)
CoastId = NewType("CoastId", str)
SavedViewId = NewType("SavedViewId", str)
```

Paths cross only repository-facing contracts and use validated absolute-path values:

```python
@dataclass(frozen=True, slots=True)
class GameLocation:
    path: Path
```

### Operations

Contracts are synchronous Python protocols.
The User Interface may schedule slow calls away from its event thread without changing their semantics.

Read operations return snapshots.
Mutation operations accept the `Revision` from the snapshot on which the change was based and return a new revision.

### Failures

Expected problems in user-supplied orders or map configuration are returned as structured issues.
Operational failures cross subsystem boundaries through application-defined exceptions:

```python
class ApplicationError(Exception): ...
class RepositoryError(ApplicationError): ...
class RevisionConflict(RepositoryError): ...
class InvalidStoredData(RepositoryError): ...
class MapLibraryError(ApplicationError): ...
class RulesEngineError(ApplicationError): ...
class RenderingError(ApplicationError): ...
```

Adapters translate dependency-specific exceptions before they cross a subsystem boundary.
Mutation failures expose no partially committed result.

## Core Values

### Map Definition

```python
class TerritoryKind(Enum):
    LAND = "land"
    SEA = "sea"

class UnitType(Enum):
    ARMY = "army"
    FLEET = "fleet"

@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float

@dataclass(frozen=True, slots=True)
class Location:
    territory_id: TerritoryId
    coast_id: CoastId | None = None

@dataclass(frozen=True, slots=True)
class TerritoryDefinition:
    id: TerritoryId
    name: str
    display_name: str
    abbreviation: str
    kind: TerritoryKind
    svg_element_id: str
    split_coast_ids: tuple[CoastId, ...]
    is_supply_centre: bool

@dataclass(frozen=True, slots=True)
class Adjacency:
    origin: Location
    destination: Location
    unit_type: UnitType

@dataclass(frozen=True, slots=True)
class PowerDefinition:
    id: PowerId
    name: str
    colour: str
    home_supply_centres: frozenset[TerritoryId]

@dataclass(frozen=True, slots=True)
class MapAssets:
    map_svg: bytes
    army_svg: bytes
    fleet_svg: bytes

@dataclass(frozen=True, slots=True)
class MapPresentation:
    label_anchors: Mapping[TerritoryId, Point]
    abbreviation_anchors: Mapping[TerritoryId, Point]
    army_anchors: Mapping[TerritoryId, Point]
    fleet_anchors: Mapping[Location, Point]
    coast_label_anchors: Mapping[Location, Point]
    coast_label_rotations: Mapping[Location, float]
    supply_centre_anchors: Mapping[TerritoryId, Point]
    territory_label_font_size: float
    coast_label_font_size: float
    inaccessible_region_colour: str
    sea_colour: str
    unclaimed_region_colour: str

@dataclass(frozen=True, slots=True)
class MapDefinition:
    id: MapId
    name: str
    territories: tuple[TerritoryDefinition, ...]
    adjacencies: frozenset[Adjacency]
    powers: tuple[PowerDefinition, ...]
    default_starting_setup: StartingSetup
    presentation: MapPresentation
    inaccessible_svg_element_ids: frozenset[str]
    assets: MapAssets
    rules_engine_id: str
```

Impassable and decorative SVG regions remain in the sanitised map asset but have no `TerritoryDefinition`.
Named coasts appear as `Location` values with a `coast_id`; ordinary coastal provinces use a location without one.

### Game and Phase State

```python
class Season(Enum):
    SPRING = "spring"
    SUMMER = "summer"
    FALL = "fall"
    WINTER = "winter"
    YEAR_END = "year_end"

@dataclass(frozen=True, slots=True, order=True)
class PhaseId:
    year: int
    season: Season

@dataclass(frozen=True, slots=True)
class UnitPosition:
    power_id: PowerId
    unit_type: UnitType
    location: Location

@dataclass(frozen=True, slots=True)
class DislodgedUnit:
    unit: UnitPosition
    retreat_options: tuple[Location, ...]

@dataclass(frozen=True, slots=True)
class GameState:
    units: tuple[UnitPosition, ...]
    dislodged_units: tuple[DislodgedUnit, ...]
    territory_controllers: Mapping[TerritoryId, PowerId | None]
    supply_centre_owners: Mapping[TerritoryId, PowerId | None]

@dataclass(frozen=True, slots=True)
class StartingSetup:
    phase_id: PhaseId
    state: GameState

@dataclass(frozen=True, slots=True)
class Revision:
    value: str

@dataclass(frozen=True, slots=True)
class GameSettings:
    visibility_policy: VisibilityPolicy
    explain_adjudication_outcomes: bool

@dataclass(frozen=True, slots=True)
class GameSnapshot:
    game_id: GameId
    name: str
    location: GameLocation
    map_definition: MapDefinition
    settings: GameSettings
    current_phase: PhaseId
    phases: tuple[PhaseId, ...]
    saved_views: tuple[SavedView, ...]
    revision: Revision

@dataclass(frozen=True, slots=True)
class PhaseSnapshot:
    game_id: GameId
    phase_id: PhaseId
    state: GameState
    submissions: Mapping[PowerId, OrderSubmission]
    results: tuple[OrderResult, ...]
    revision: Revision
```

`GameSnapshot` contains configuration and the phase index.
`PhaseSnapshot` contains the independently loadable record for one phase.

### Orders

Canonical orders are a discriminated union:

```python
@dataclass(frozen=True, slots=True)
class UnitRef:
    power_id: PowerId
    unit_type: UnitType
    location: Location

@dataclass(frozen=True, slots=True)
class HoldOrder:
    unit: UnitRef

@dataclass(frozen=True, slots=True)
class MoveOrder:
    unit: UnitRef
    destination: Location
    via_convoy: bool

@dataclass(frozen=True, slots=True)
class SupportOrder:
    unit: UnitRef
    supported_unit: UnitRef
    destination: Location | None

@dataclass(frozen=True, slots=True)
class ConvoyOrder:
    unit: UnitRef
    convoyed_army: UnitRef
    destination: Location

@dataclass(frozen=True, slots=True)
class RetreatOrder:
    unit: UnitRef
    destination: Location

@dataclass(frozen=True, slots=True)
class BuildOrder:
    unit: UnitRef

@dataclass(frozen=True, slots=True)
class DisbandOrder:
    unit: UnitRef

@dataclass(frozen=True, slots=True)
class WaiveOrder:
    power_id: PowerId

CanonicalOrder = (
    HoldOrder
    | MoveOrder
    | SupportOrder
    | ConvoyOrder
    | RetreatOrder
    | BuildOrder
    | DisbandOrder
    | WaiveOrder
)
```

A support order with `destination=None` supports the referenced unit to hold.

Submitted and interpreted forms remain separate:

```python
class IssueSeverity(Enum):
    WARNING = "warning"
    ERROR = "error"

@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    message: str
    severity: IssueSeverity

@dataclass(frozen=True, slots=True)
class SourceLine:
    number: int
    text: str

@dataclass(frozen=True, slots=True)
class OrderCandidate:
    source: SourceLine
    order: CanonicalOrder | None
    canonical_text: str | None
    parser_issues: tuple[Issue, ...]

@dataclass(frozen=True, slots=True)
class RuleValidation:
    source_line: int
    is_valid: bool
    issues: tuple[Issue, ...]
    effective_order: CanonicalOrder | None

@dataclass(frozen=True, slots=True)
class SubmissionLine:
    candidate: OrderCandidate
    validation: RuleValidation | None

@dataclass(frozen=True, slots=True)
class OrderSubmission:
    power_id: PowerId
    raw_text: str
    lines: tuple[SubmissionLine, ...]
    is_final: bool

@dataclass(frozen=True, slots=True)
class EffectiveOrder:
    power_id: PowerId
    source_line: int | None
    submitted_order: CanonicalOrder | None
    order: CanonicalOrder
    is_valid: bool | None

@dataclass(frozen=True, slots=True)
class OrderResult:
    power_id: PowerId
    source_line: int | None
    order: CanonicalOrder
    outcome_codes: tuple[str, ...]
```

An unrecognised source line has no canonical order or rule validation.
A recognised invalid order carries the Rules Engine's phase-specific replacement when that replacement corresponds to the source line.
An `EffectiveOrder` uses the submitted order when valid and the standard phase-specific replacement when invalid or omitted.
Synthesised movement holds, retreat disbands, waived builds and automatic disbands have `source_line=None` unless they directly replace a recognised invalid line.

### Phase Requirements and Adjudication

```python
@dataclass(frozen=True, slots=True)
class PowerPhaseRequirement:
    power_id: PowerId
    units_requiring_orders: tuple[UnitRef, ...]
    build_count: int
    disband_count: int

    @property
    def requires_submission(self) -> bool: ...

@dataclass(frozen=True, slots=True)
class PhaseRequirements:
    phase_id: PhaseId
    by_power: Mapping[PowerId, PowerPhaseRequirement]

@dataclass(frozen=True, slots=True)
class AdjudicationProposal:
    completed_phase: PhaseId
    next_phase: PhaseId
    next_state: GameState
    results: tuple[OrderResult, ...]
```

An `AdjudicationProposal` is inert until committed by the Game Repository.

### Visibility and Rendering

```python
class PerspectiveKind(Enum):
    GAMEMASTER = "gamemaster"
    POWER = "power"

@dataclass(frozen=True, slots=True)
class Perspective:
    kind: PerspectiveKind
    power_id: PowerId | None

@dataclass(frozen=True, slots=True)
class VisibilityPolicy:
    enabled: bool
    adjacency_depth: int

@dataclass(frozen=True, slots=True)
class HiddenTerritory:
    territory_id: TerritoryId
    label: str

@dataclass(frozen=True, slots=True)
class VisibleTerritory:
    territory_id: TerritoryId
    label: str
    controller: PowerId | None
    supply_centre_owner: PowerId | None
    unit: UnitPosition | None
    dislodged_unit: UnitPosition | None

ProjectedTerritory = HiddenTerritory | VisibleTerritory

@dataclass(frozen=True, slots=True)
class ProjectedOrder:
    source_line: int | None
    order: CanonicalOrder
    is_valid: bool | None

@dataclass(frozen=True, slots=True)
class ProjectedMapState:
    phase_id: PhaseId
    perspective: Perspective
    territories: tuple[ProjectedTerritory, ...]
    orders: tuple[ProjectedOrder, ...]
    results: tuple[OrderResult, ...]

class DisplayMode(Enum):
    POSITION = "position"
    ORDERS = "orders"

class LabelMode(Enum):
    FULL_NAME = "full_name"
    ABBREVIATION = "abbreviation"

@dataclass(frozen=True, slots=True)
class MapBounds:
    x: float
    y: float
    width: float
    height: float

@dataclass(frozen=True, slots=True)
class PixelSize:
    width: int
    height: int

@dataclass(frozen=True, slots=True)
class RenderRequest:
    display_mode: DisplayMode
    label_mode: LabelMode
    bounds: MapBounds
    output_size: PixelSize

@dataclass(frozen=True, slots=True)
class MapHotspot:
    source_line: int | None
    path: tuple[Point, ...]
    hit_width: float
    outcome_codes: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class MapScene:
    svg: bytes
    map_bounds: MapBounds
    hotspots: tuple[MapHotspot, ...]

@dataclass(frozen=True, slots=True)
class ImageArtifact:
    media_type: str
    data: bytes
    size: PixelSize

@dataclass(frozen=True, slots=True)
class SavedView:
    id: SavedViewId
    name: str
    bounds: MapBounds
    aspect_ratio: float
    output_size: PixelSize
```

`Perspective.power_id` is present exactly when `kind` is `POWER`.
The projected-territory union prevents hidden territories from carrying controller, supply-centre or unit fields.
`ProjectedOrder.order` is the submitted canonical order when valid and the phase-specific effective order when invalid or omitted.
`MapScene.svg` is sanitised, self-contained SVG content suitable for display by the User Interface.
`MapScene.hotspots` contains only projected outcome information and is empty when optional adjudication explanations are disabled.

### Application and Map-Import Values

```python
@dataclass(frozen=True, slots=True)
class GameSummary:
    game_id: GameId
    name: str
    location: GameLocation
    current_phase: PhaseId

@dataclass(frozen=True, slots=True)
class MapSummary:
    map_id: MapId
    name: str
    power_count: int

@dataclass(frozen=True, slots=True)
class NewGameRequest:
    name: str
    location: GameLocation
    map_id: MapId
    starting_setup: StartingSetup

@dataclass(frozen=True, slots=True)
class NewGameDraft:
    map_id: MapId
    map_name: str
    starting_setup: StartingSetup

@dataclass(frozen=True, slots=True)
class CreateStoredGame:
    name: str
    location: GameLocation
    map_definition: MapDefinition
    starting_setup: StartingSetup

@dataclass(frozen=True, slots=True)
class SessionView:
    game: GameSnapshot | None
    phase: PhaseSnapshot | None
    selected_perspective: Perspective
    phase_requirements: PhaseRequirements | None
    recent_games: tuple[GameSummary, ...]

class SvgElementRole(Enum):
    TERRITORY = "territory"
    IMPASSABLE = "impassable"
    DECORATION = "decoration"

@dataclass(frozen=True, slots=True)
class MapDraft:
    map_id: MapId
    name: str
    svg: bytes
    element_roles: Mapping[str, SvgElementRole]
    territories: tuple[TerritoryDefinition, ...]
    map_yaml: str
    powers: tuple[PowerDefinition, ...]
    default_starting_setup: StartingSetup
    presentation: MapPresentation
    army_svg: bytes | None
    fleet_svg: bytes | None
    rules_engine_id: str

@dataclass(frozen=True, slots=True)
class IssueLocation:
    field: str
    item_id: str | None = None
    line: int | None = None

@dataclass(frozen=True, slots=True)
class LocatedIssue:
    issue: Issue
    location: IssueLocation

@dataclass(frozen=True, slots=True)
class MapValidation:
    issues: tuple[LocatedIssue, ...]

    @property
    def is_valid(self) -> bool: ...

@dataclass(frozen=True, slots=True)
class AdvancedPhase:
    session: SessionView

@dataclass(frozen=True, slots=True)
class FinalisationRequired:
    unfinalised_powers: tuple[PowerId, ...]

ResolveResult = AdvancedPhase | FinalisationRequired
```

`MapDraft.map_yaml` is the single authored map document and includes local additions and removals from geometry-derived ordinary adjacency.
The Map Library combines those exceptions with inferred connections to create `MapDefinition.adjacencies` after successful validation.
Recent-game ordering is significant, with the most recently opened game first.

## Application Service Contract

The Application Coordinator provides the sole API consumed by the User Interface:

```python
class ApplicationService(Protocol):
    def start(self) -> SessionView: ...
    def open_game(self, location: GameLocation) -> SessionView: ...
    def prepare_new_game(self, map_id: MapId) -> NewGameDraft: ...
    def create_game(self, request: NewGameRequest) -> SessionView: ...
    def select_phase(self, phase_id: PhaseId) -> SessionView: ...
    def select_perspective(self, perspective: Perspective) -> SessionView: ...

    def update_orders(self, power_id: PowerId, raw_text: str) -> PhaseSnapshot: ...
    def set_orders_final(self, power_id: PowerId, is_final: bool) -> PhaseSnapshot: ...
    def resolve_and_advance(self, allow_unfinalised: bool = False) -> ResolveResult: ...

    def compose_map(self, request: RenderRequest) -> MapScene: ...
    def export_map(self, request: RenderRequest) -> ImageArtifact: ...
    def save_view(self, view: SavedView) -> GameSnapshot: ...
    def delete_view(self, view_id: SavedViewId) -> GameSnapshot: ...
    def begin_game_map_placement(self) -> MapDraft: ...
    def save_game_map_placement(self, draft: MapDraft) -> SessionView: ...

    def list_maps(self) -> tuple[MapSummary, ...]: ...
    def begin_map_import(self, name: str, svg: bytes) -> MapDraft: ...
    def load_map_draft(self, map_id: MapId) -> MapDraft: ...
    def validate_map_draft(self, draft: MapDraft) -> MapValidation: ...
    def save_map_draft(self, draft: MapDraft) -> MapDefinition: ...
```

`SessionView` identifies the active game, selected phase, selected perspective and available navigation choices.
`prepare_new_game` returns the reusable map's default setup for game-specific editing.
`create_game` validates the supplied setup against the unchanged powers, colours, home supply centres and topology before creating files.
`load_map_draft` opens an existing reusable map for configuration and visual anchor placement without re-importing its SVG.
Saving that draft replaces only the reusable map; private map snapshots already stored in games remain unchanged.
Current-game placement loads a restricted draft and persists only its presentation anchors, named-coast label rotations, shared label sizes and neutral map colours into that game's private snapshot.
`ResolveResult` is either an `AdvancedPhase` or a `FinalisationRequired` value naming powers whose orders are still open.
Calling `resolve_and_advance(allow_unfinalised=True)` authorises advancement after that warning.

## Game Repository Contract

```python
class GameRepository(Protocol):
    def recent_games(self) -> tuple[GameSummary, ...]: ...
    def last_opened(self) -> GameLocation | None: ...
    def open(self, location: GameLocation) -> GameSnapshot: ...
    def load_phase(self, game_id: GameId, phase_id: PhaseId) -> PhaseSnapshot: ...

    def create(self, request: CreateStoredGame) -> GameSnapshot: ...
    def save_submission(
        self,
        game_id: GameId,
        phase_id: PhaseId,
        submission: OrderSubmission,
        expected_revision: Revision,
    ) -> PhaseSnapshot: ...
    def set_final(
        self,
        game_id: GameId,
        phase_id: PhaseId,
        power_id: PowerId,
        is_final: bool,
        expected_revision: Revision,
    ) -> PhaseSnapshot: ...
    def save_view(
        self,
        game_id: GameId,
        view: SavedView,
        expected_revision: Revision,
    ) -> GameSnapshot: ...
    def delete_view(
        self,
        game_id: GameId,
        view_id: SavedViewId,
        expected_revision: Revision,
    ) -> GameSnapshot: ...
    def load_map_placement_draft(self, game_id: GameId) -> MapDraft: ...
    def save_map_presentation(
        self,
        game_id: GameId,
        presentation: MapPresentation,
        expected_revision: Revision,
    ) -> GameSnapshot: ...
    def commit_adjudication(
        self,
        game_id: GameId,
        proposal: AdjudicationProposal,
        expected_revision: Revision,
    ) -> GameSnapshot: ...
```

Every mutation validates the supplied revision immediately before commit.
`commit_adjudication` makes the completed phase results and next phase state visible together.

## Map Library Contract

```python
class MapLibrary(Protocol):
    def list(self) -> tuple[MapSummary, ...]: ...
    def load(self, map_id: MapId) -> MapDefinition: ...
    def load_draft(self, map_id: MapId) -> MapDraft: ...
    def import_svg(self, name: str, svg: bytes) -> MapDraft: ...
    def validate(self, draft: MapDraft) -> MapValidation: ...
    def validate_starting_setup(
        self,
        map_definition: MapDefinition,
        starting_setup: StartingSetup,
    ) -> MapValidation: ...
    def save(self, draft: MapDraft) -> MapDefinition: ...
```

`MapDraft` contains the sanitised SVG, element classifications, generated topology, configuration and presentation anchors.
`MapValidation` contains structured issues with stable codes and locations within the draft or topology text.
`validate_starting_setup` checks a game-specific phase, units, ownership and control without permitting changes to powers, colours, home supply centres or topology.
`save` accepts a draft only when validation contains no errors.

## Order Processor Contract

```python
class OrderProcessor(Protocol):
    def interpret(
        self,
        map_definition: MapDefinition,
        power_id: PowerId,
        raw_text: str,
    ) -> tuple[OrderCandidate, ...]: ...

    def prepare_submission(
        self,
        map_definition: MapDefinition,
        phase: PhaseSnapshot,
        power_id: PowerId,
        raw_text: str,
    ) -> OrderSubmission: ...
```

The Order Processor receives a `RulesEngine` implementation when constructed.
`prepare_submission` calls `interpret`, sends recognised candidates to `RulesEngine.validate`, then combines results by source-line number.
The returned submission is open; finalisation is a distinct repository mutation.

## Rules Engine Contract

```python
class RulesEngine(Protocol):
    @property
    def engine_id(self) -> str: ...

    def describe_phase(
        self,
        map_definition: MapDefinition,
        phase_id: PhaseId,
        state: GameState,
    ) -> PhaseRequirements: ...

    def validate(
        self,
        map_definition: MapDefinition,
        phase_id: PhaseId,
        state: GameState,
        power_id: PowerId,
        candidates: tuple[OrderCandidate, ...],
    ) -> tuple[RuleValidation, ...]: ...

    def effective_orders(
        self,
        map_definition: MapDefinition,
        phase: PhaseSnapshot,
    ) -> tuple[EffectiveOrder, ...]: ...

    def adjudicate(
        self,
        map_definition: MapDefinition,
        phase: PhaseSnapshot,
    ) -> AdjudicationProposal: ...
```

`validate` returns one result for every recognised candidate and preserves its source-line number.
`effective_orders` combines every power's submission with phase requirements and applies standard phase-specific defaults.
Movement defaults hold, retreat defaults disband, unused builds waive and missing disbands are selected by the standard automatic-disband rules.
`adjudicate` resolves that same effective order set and produces package-independent result codes.
The engine receives no repository or UI dependency.

## Visibility Projector Contract

```python
@dataclass(frozen=True, slots=True)
class ProjectionRequest:
    perspective: Perspective
    label_mode: LabelMode
    include_orders: bool
    include_results: bool

class VisibilityProjector(Protocol):
    def project(
        self,
        map_definition: MapDefinition,
        phase: PhaseSnapshot,
        effective_orders: tuple[EffectiveOrder, ...],
        policy: VisibilityPolicy,
        request: ProjectionRequest,
    ) -> ProjectedMapState: ...
```

For a power perspective, the projector calculates visibility over the union of army and fleet territory connections, including exceptional links, and filters territories, units, supply-centre owners, orders and results before constructing the return value.
The selected power's active and dislodged units both act as visibility origins.
For the gamemaster perspective, it constructs the same return type with every territory visible.

## Map Renderer Contract

```python
class MapRenderer(Protocol):
    def compose(
        self,
        map_definition: MapDefinition,
        projected_state: ProjectedMapState,
        request: RenderRequest,
    ) -> MapScene: ...

    def export(
        self,
        scene: MapScene,
        request: RenderRequest,
    ) -> ImageArtifact: ...
```

`compose` creates a self-contained SVG scene using only the projected state.
`export` clips to the intersection of the requested bounds and the map bounds and emits a PNG at the requested pixel size.

## Compatibility Rules

- Adding an optional field with a defined default is a compatible contract change.
- Renaming identifiers, changing field meaning or broadening a subsystem's ownership requires coordinated contract and design updates.
- Implementations accept and return application-owned values at their public boundary.
- A replacement Rules Engine declares a distinct `engine_id` and satisfies the same phase-description, validation, effective-order and adjudication semantics.
- Stored-file schema evolution is owned by the corresponding repository and remains outside these in-process contracts.
