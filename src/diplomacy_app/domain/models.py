"""Immutable values shared by all application subsystems.

These types intentionally contain no Qt, filesystem-serialization, or bundled
rules-engine objects. They are the executable form of ``docs/api-contracts.md``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NewType

GameId = NewType("GameId", str)
MapId = NewType("MapId", str)
PowerId = NewType("PowerId", str)
TerritoryId = NewType("TerritoryId", str)
CoastId = NewType("CoastId", str)
SavedViewId = NewType("SavedViewId", str)


def game_folder_name(name: str) -> str:
    """Return the stable filesystem and identifier slug for a game name."""
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "game"


class TerritoryKind(StrEnum):
    LAND = "land"
    SEA = "sea"


class UnitType(StrEnum):
    ARMY = "army"
    FLEET = "fleet"


class Season(StrEnum):
    SPRING = "spring"
    SUMMER = "summer"
    FALL = "fall"
    WINTER = "winter"
    YEAR_END = "year_end"


class IssueSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class PerspectiveKind(StrEnum):
    GAMEMASTER = "gamemaster"
    POWER = "power"


class DisplayMode(StrEnum):
    POSITION = "position"
    ORDERS = "orders"


class LabelMode(StrEnum):
    FULL_NAME = "full_name"
    ABBREVIATION = "abbreviation"


class SvgElementRole(StrEnum):
    TERRITORY = "territory"
    IMPASSABLE = "impassable"
    DECORATION = "decoration"


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True, slots=True, order=True)
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
    label_colour: str
    inaccessible_region_colour: str
    sea_colour: str
    unclaimed_region_colour: str


@dataclass(frozen=True, slots=True, order=True)
class PhaseId:
    year: int
    season: Season

    @property
    def label(self) -> str:
        name = "Year End" if self.season is Season.YEAR_END else self.season.value.title()
        return f"{name} {self.year}"


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


@dataclass(frozen=True, slots=True)
class GameLocation:
    path: Path

    def __post_init__(self) -> None:
        if not self.path.is_absolute():
            raise ValueError("Game locations must be absolute paths")


@dataclass(frozen=True, slots=True)
class Revision:
    value: str


@dataclass(frozen=True, slots=True)
class VisibilityPolicy:
    enabled: bool = False
    adjacency_depth: int = 1


@dataclass(frozen=True, slots=True)
class GameSettings:
    visibility_policy: VisibilityPolicy = VisibilityPolicy()
    explain_adjudication_outcomes: bool = False


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
    via_convoy: bool = False


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


type CanonicalOrder = (
    HoldOrder
    | MoveOrder
    | SupportOrder
    | ConvoyOrder
    | RetreatOrder
    | BuildOrder
    | DisbandOrder
    | WaiveOrder
)


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
    is_final: bool = False


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


@dataclass(frozen=True, slots=True)
class PhaseSnapshot:
    game_id: GameId
    phase_id: PhaseId
    state: GameState
    submissions: Mapping[PowerId, OrderSubmission]
    results: tuple[OrderResult, ...]
    revision: Revision


@dataclass(frozen=True, slots=True)
class PowerPhaseRequirement:
    power_id: PowerId
    units_requiring_orders: tuple[UnitRef, ...]
    build_count: int = 0
    disband_count: int = 0

    @property
    def requires_submission(self) -> bool:
        return bool(self.units_requiring_orders or self.build_count or self.disband_count)


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


@dataclass(frozen=True, slots=True)
class Perspective:
    kind: PerspectiveKind
    power_id: PowerId | None = None

    def __post_init__(self) -> None:
        if (self.kind is PerspectiveKind.POWER) != (self.power_id is not None):
            raise ValueError("A power perspective must identify exactly one power")


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


type ProjectedTerritory = HiddenTerritory | VisibleTerritory


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
    settings: GameSettings = GameSettings()


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
    settings: GameSettings = GameSettings()


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
    def is_valid(self) -> bool:
        return not any(item.issue.severity is IssueSeverity.ERROR for item in self.issues)


@dataclass(frozen=True, slots=True)
class ProjectionRequest:
    perspective: Perspective
    label_mode: LabelMode
    include_orders: bool
    include_results: bool


@dataclass(frozen=True, slots=True)
class SessionView:
    game: GameSnapshot | None
    phase: PhaseSnapshot | None
    selected_perspective: Perspective
    phase_requirements: PhaseRequirements | None
    recent_games: tuple[GameSummary, ...]


@dataclass(frozen=True, slots=True)
class AdvancedPhase:
    session: SessionView


@dataclass(frozen=True, slots=True)
class FinalisationRequired:
    unfinalised_powers: tuple[PowerId, ...]


type ResolveResult = AdvancedPhase | FinalisationRequired


GAMEMASTER = Perspective(PerspectiveKind.GAMEMASTER)
