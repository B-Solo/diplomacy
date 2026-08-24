"""Filesystem implementation of the Game Repository contract."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from diplomacy_app.domain.errors import InvalidStoredData, RepositoryError, RevisionConflict
from diplomacy_app.domain.models import (
    AdjudicationProposal,
    CreateStoredGame,
    GameId,
    GameLocation,
    GameSnapshot,
    GameSummary,
    MapDraft,
    MapPresentation,
    OrderResult,
    OrderSubmission,
    PhaseId,
    PhaseSnapshot,
    PowerId,
    Revision,
    SavedView,
    SavedViewId,
    Season,
    SvgElementRole,
)
from diplomacy_app.game_repository.game_codec import (
    authored_map_yaml,
    game_config_data,
    load_game_config,
    load_private_map,
    load_views,
    views_data,
)
from diplomacy_app.game_repository.recent_games import RecentGameStore
from diplomacy_app.game_repository.revision import revision_for_game
from diplomacy_app.game_repository.transaction import atomic_json, commit_files, recover
from diplomacy_app.storage.serialization import (
    map_definition_data,
    orders_document_data,
    orders_document_from_data,
    state_data,
    state_from_data,
)

_SEASON_DIRECTORIES = {
    Season.SPRING: "Spring",
    Season.SUMMER: "Summer",
    Season.FALL: "Fall",
    Season.WINTER: "Winter",
    Season.YEAR_END: "YearEnd",
}
_SEASON_ORDER = {season: index for index, season in enumerate(Season)}


def _phase_key(value: PhaseId) -> tuple[int, int]:
    return value.year, _SEASON_ORDER[value.season]


def _phase_directory(root: Path, phase: PhaseId) -> Path:
    return root / str(phase.year) / _SEASON_DIRECTORIES[phase.season]


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


class FileGameRepository:
    """Persist games as portable, independently reopenable folders."""

    def __init__(self, recent_store: RecentGameStore | None = None) -> None:
        self._recent = recent_store or RecentGameStore()
        self._locations: dict[GameId, GameLocation] = {}

    def _remember(self, game_id: GameId, location: GameLocation) -> None:
        self._locations[game_id] = location
        self._recent.record(location)

    def last_opened(self) -> GameLocation | None:
        return self._recent.last_opened()

    def recent_games(self) -> tuple[GameSummary, ...]:
        summaries: list[GameSummary] = []
        for location in self._recent.locations():
            if not location.path.exists():
                continue
            try:
                snapshot = self._read_game(location, record=False)
                summaries.append(
                    GameSummary(snapshot.game_id, snapshot.name, location, snapshot.current_phase)
                )
            except (RepositoryError, OSError):
                continue
        return tuple(summaries)

    def _phase_ids(self, root: Path) -> tuple[PhaseId, ...]:
        phases: list[PhaseId] = []
        for state_path in root.glob("[0-9]*/**/state.json"):
            try:
                value = json.loads(state_path.read_text(encoding="utf-8"))
                phase, _ = state_from_data(value)
                phases.append(phase)
            except (OSError, ValueError, InvalidStoredData) as exc:
                raise InvalidStoredData(f"Invalid phase state {state_path}: {exc}") from exc
        if not phases:
            raise InvalidStoredData("Game contains no phase state")
        return tuple(sorted(set(phases), key=_phase_key))

    def _read_game(self, location: GameLocation, *, record: bool) -> GameSnapshot:
        root = location.path
        if not root.is_dir():
            raise RepositoryError(f"Game folder is unavailable: {root}")
        recover(root)
        game_id, name, settings = load_game_config(root)
        phases = self._phase_ids(root)
        snapshot = GameSnapshot(
            game_id,
            name,
            location,
            load_private_map(root),
            settings,
            phases[-1],
            phases,
            load_views(root),
            revision_for_game(root),
        )
        self._locations[game_id] = location
        if record:
            self._remember(game_id, location)
        return snapshot

    def open(self, location: GameLocation) -> GameSnapshot:
        return self._read_game(location, record=True)

    def _root_for(self, game_id: GameId) -> Path:
        location = self._locations.get(game_id)
        if location is None:
            for recent in self._recent.locations():
                try:
                    found, _, _ = load_game_config(recent.path)
                    if found == game_id:
                        self._locations[game_id] = recent
                        location = recent
                        break
                except (OSError, InvalidStoredData):
                    continue
        if location is None:
            raise RepositoryError(f"Game is not open: {game_id}")
        return location.path

    def load_phase(self, game_id: GameId, phase_id: PhaseId) -> PhaseSnapshot:
        root = self._root_for(game_id)
        recover(root)
        state_path = _phase_directory(root, phase_id) / "state.json"
        try:
            loaded_phase, state = state_from_data(
                json.loads(state_path.read_text(encoding="utf-8"))
            )
            if loaded_phase != phase_id:
                raise InvalidStoredData(f"Phase path and document disagree at {state_path}")
            orders_path = state_path.with_name("orders.json")
            submissions: dict[PowerId, OrderSubmission] = {}
            results: tuple[OrderResult, ...] = ()
            if orders_path.exists():
                submissions, results = orders_document_from_data(
                    json.loads(orders_path.read_text(encoding="utf-8"))
                )
            return PhaseSnapshot(
                game_id,
                phase_id,
                state,
                MappingProxyType(submissions),
                results,
                revision_for_game(root),
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            if isinstance(exc, InvalidStoredData):
                raise
            raise InvalidStoredData(f"Could not load phase {phase_id.label}: {exc}") from exc

    def load_map_placement_draft(self, game_id: GameId) -> MapDraft:
        self._root_for(game_id)
        game = self._read_game(self._locations[game_id], record=False)
        definition = game.map_definition
        return MapDraft(
            definition.id,
            definition.name,
            definition.assets.map_svg,
            MappingProxyType(
                {
                    territory.svg_element_id: SvgElementRole.TERRITORY
                    for territory in definition.territories
                }
            ),
            definition.territories,
            authored_map_yaml(definition),
            definition.powers,
            definition.default_starting_setup,
            definition.presentation,
            definition.assets.army_svg,
            definition.assets.fleet_svg,
            definition.rules_engine_id,
        )

    def create(self, request: CreateStoredGame) -> GameSnapshot:
        target = request.location.path
        if target.exists() and any(target.iterdir()):
            raise RepositoryError(f"Game folder is not empty: {target}")
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True)
        game_slug = re.sub(r"[^a-z0-9]+", "-", request.name.casefold()).strip("-") or "game"
        game_id = GameId(game_slug)
        private_map = replace(request.map_definition, default_starting_setup=request.starting_setup)
        stage = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=parent))
        try:
            (stage / "map").mkdir()
            settings = request.settings
            (stage / "game.yaml").write_text(
                game_config_data(game_id, request.name, settings), encoding="utf-8"
            )
            atomic_json(stage / "views.json", views_data(()))
            (stage / "map" / "map.yaml").write_text(
                authored_map_yaml(private_map), encoding="utf-8"
            )
            (stage / "map" / "map.svg").write_bytes(private_map.assets.map_svg)
            (stage / "map" / "army.svg").write_bytes(private_map.assets.army_svg)
            (stage / "map" / "fleet.svg").write_bytes(private_map.assets.fleet_svg)
            atomic_json(stage / "map" / "_compiled-map.json", map_definition_data(private_map))
            first = _phase_directory(stage, request.starting_setup.phase_id)
            first.mkdir(parents=True)
            atomic_json(
                first / "state.json",
                state_data(request.starting_setup.state, request.starting_setup.phase_id),
            )
            (stage / ".transactions").mkdir()
            if target.exists():
                target.rmdir()
            os.replace(stage, target)
        except OSError as exc:
            if stage.exists():
                shutil.rmtree(stage)
            raise RepositoryError(f"Could not create game: {exc}") from exc
        return self.open(request.location)

    def _check_revision(self, root: Path, expected: Revision) -> None:
        actual = revision_for_game(root)
        if actual != expected:
            raise RevisionConflict(
                "The game changed since this view was loaded; reopen it before saving"
            )

    def save_submission(
        self,
        game_id: GameId,
        phase_id: PhaseId,
        submission: OrderSubmission,
        expected_revision: Revision,
    ) -> PhaseSnapshot:
        root = self._root_for(game_id)
        self._check_revision(root, expected_revision)
        phase = self.load_phase(game_id, phase_id)
        submissions = dict(phase.submissions)
        submissions[submission.power_id] = submission
        atomic_json(
            _phase_directory(root, phase_id) / "orders.json",
            orders_document_data(submissions, phase.results),
        )
        return self.load_phase(game_id, phase_id)

    def set_final(
        self,
        game_id: GameId,
        phase_id: PhaseId,
        power_id: PowerId,
        is_final: bool,
        expected_revision: Revision,
    ) -> PhaseSnapshot:
        root = self._root_for(game_id)
        self._check_revision(root, expected_revision)
        phase = self.load_phase(game_id, phase_id)
        submission = phase.submissions.get(power_id, OrderSubmission(power_id, "", (), False))
        submissions = dict(phase.submissions)
        submissions[power_id] = replace(submission, is_final=is_final)
        atomic_json(
            _phase_directory(root, phase_id) / "orders.json",
            orders_document_data(submissions, phase.results),
        )
        return self.load_phase(game_id, phase_id)

    def save_view(
        self, game_id: GameId, view: SavedView, expected_revision: Revision
    ) -> GameSnapshot:
        root = self._root_for(game_id)
        self._check_revision(root, expected_revision)
        location = self._locations[game_id]
        game = self._read_game(location, record=False)
        views = [item for item in game.saved_views if item.id != view.id]
        views.append(view)
        atomic_json(root / "views.json", views_data(tuple(views)))
        return self._read_game(location, record=False)

    def delete_view(
        self, game_id: GameId, view_id: SavedViewId, expected_revision: Revision
    ) -> GameSnapshot:
        root = self._root_for(game_id)
        self._check_revision(root, expected_revision)
        location = self._locations[game_id]
        game = self._read_game(location, record=False)
        views = tuple(item for item in game.saved_views if item.id != view_id)
        atomic_json(root / "views.json", views_data(views))
        return self._read_game(location, record=False)

    def save_map_presentation(
        self,
        game_id: GameId,
        presentation: MapPresentation,
        expected_revision: Revision,
    ) -> GameSnapshot:
        root = self._root_for(game_id)
        self._check_revision(root, expected_revision)
        location = self._locations[game_id]
        game = self._read_game(location, record=False)
        current = game.map_definition.presentation
        fields = (
            "label_anchors",
            "abbreviation_anchors",
            "army_anchors",
            "fleet_anchors",
            "coast_label_anchors",
            "coast_label_rotations",
            "supply_centre_anchors",
        )
        if any(
            set(getattr(current, field)) != set(getattr(presentation, field)) for field in fields
        ):
            raise RepositoryError("Game map placement cannot add or remove visual anchors")
        points = (
            *presentation.label_anchors.values(),
            *presentation.abbreviation_anchors.values(),
            *presentation.army_anchors.values(),
            *presentation.fleet_anchors.values(),
            *presentation.coast_label_anchors.values(),
            *presentation.supply_centre_anchors.values(),
        )
        values = (
            *(coordinate for point in points for coordinate in (point.x, point.y)),
            *presentation.coast_label_rotations.values(),
            presentation.territory_label_font_size,
            presentation.coast_label_font_size,
        )
        if not all(math.isfinite(value) for value in values):
            raise RepositoryError("Game map placement values must be finite")
        if not all(
            5 <= size <= 24
            for size in (
                presentation.territory_label_font_size,
                presentation.coast_label_font_size,
            )
        ):
            raise RepositoryError("Game map label sizes must be between 5 and 24")
        colours = (
            presentation.label_colour,
            presentation.inaccessible_region_colour,
            presentation.sea_colour,
            presentation.unclaimed_region_colour,
        )
        if not all(re.fullmatch(r"#[0-9a-fA-F]{6}", colour) for colour in colours):
            raise RepositoryError("Game map colours must use #RRGGBB notation")
        updated = replace(game.map_definition, presentation=presentation)
        commit_files(
            root,
            [
                ("map/map.yaml", authored_map_yaml(updated).encode("utf-8")),
                ("map/_compiled-map.json", _json_bytes(map_definition_data(updated))),
            ],
            "map/_compiled-map.json",
        )
        return self._read_game(location, record=False)

    def commit_adjudication(
        self, game_id: GameId, proposal: AdjudicationProposal, expected_revision: Revision
    ) -> GameSnapshot:
        root = self._root_for(game_id)
        self._check_revision(root, expected_revision)
        game = self._read_game(self._locations[game_id], record=False)
        if game.current_phase != proposal.completed_phase:
            raise RepositoryError("Only the current phase can be advanced")
        completed = self.load_phase(game_id, proposal.completed_phase)
        completed_orders = orders_document_data(dict(completed.submissions), proposal.results)
        next_state = state_data(proposal.next_state, proposal.next_phase)
        completed_relative = (
            (_phase_directory(root, proposal.completed_phase) / "orders.json")
            .relative_to(root)
            .as_posix()
        )
        next_relative = (
            (_phase_directory(root, proposal.next_phase) / "state.json")
            .relative_to(root)
            .as_posix()
        )
        commit_files(
            root,
            [
                (completed_relative, _json_bytes(completed_orders)),
                (next_relative, _json_bytes(next_state)),
            ],
            next_relative,
        )
        return self._read_game(self._locations[game_id], record=False)
