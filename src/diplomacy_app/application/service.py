"""Coordinator for complete user-initiated use cases."""

from __future__ import annotations

from diplomacy_app.domain.errors import ApplicationError, MapLibraryError, RepositoryError
from diplomacy_app.domain.models import (
    GAMEMASTER,
    AdvancedPhase,
    CreateStoredGame,
    DisplayMode,
    EffectiveOrder,
    FinalisationRequired,
    GameLocation,
    GameSnapshot,
    LabelMode,
    MapBounds,
    MapDefinition,
    MapDraft,
    MapId,
    MapScene,
    MapSummary,
    MapValidation,
    NewGameDraft,
    NewGameRequest,
    OrderResult,
    OrderSubmission,
    Perspective,
    PhaseId,
    PhaseSnapshot,
    PixelSize,
    Point,
    PowerId,
    ProjectedMapState,
    ProjectionRequest,
    RenderRequest,
    ResolveResult,
    SavedView,
    SavedViewId,
    Season,
    SessionView,
    VisibleTerritory,
)
from diplomacy_app.game_repository import FileGameRepository
from diplomacy_app.map_library import FileMapLibrary
from diplomacy_app.order_processing import OrderProcessor
from diplomacy_app.rendering import MapRenderer
from diplomacy_app.rules_engine import StandardRulesEngine
from diplomacy_app.visibility import VisibilityProjector


class ApplicationService:
    """The sole application API consumed by desktop widgets."""

    def __init__(
        self,
        repository: FileGameRepository,
        map_library: FileMapLibrary,
        rules_engine: StandardRulesEngine,
        projector: VisibilityProjector,
        renderer: MapRenderer,
    ) -> None:
        self.repository = repository
        self.map_library = map_library
        self.rules_engine = rules_engine
        self.order_processor = OrderProcessor(rules_engine)
        self.projector = projector
        self.renderer = renderer
        self._game: GameSnapshot | None = None
        self._phase: PhaseSnapshot | None = None
        self._perspective = GAMEMASTER

    def _session(self) -> SessionView:
        requirements = None
        if self._game and self._phase:
            requirements = self.rules_engine.describe_phase(
                self._game.map_definition,
                self._phase.phase_id,
                self._phase.resolution_state or self._phase.state,
            )
        return SessionView(
            self._game,
            self._phase,
            self._perspective,
            requirements,
            self.repository.recent_games(),
        )

    def start(self) -> SessionView:
        location = self.repository.last_opened()
        if location and location.path.exists():
            try:
                return self.open_game(location)
            except ApplicationError:
                pass
        return self._session()

    def open_game(self, location: GameLocation) -> SessionView:
        game = self.repository.open(location)
        phase = self.repository.load_phase(game.game_id, game.current_phase)
        self._game, self._phase, self._perspective = game, phase, GAMEMASTER
        return self._session()

    def delete_game(self, location: GameLocation) -> SessionView:
        deleting_current = (
            self._game is not None and self._game.location.path.resolve() == location.path.resolve()
        )
        self.repository.delete(location)
        if deleting_current:
            self._game = None
            self._phase = None
            self._perspective = GAMEMASTER
        return self._session()

    def _require_game(self) -> tuple[GameSnapshot, PhaseSnapshot]:
        if self._game is None or self._phase is None:
            raise RepositoryError("Open or create a game first")
        return self._game, self._phase

    def prepare_new_game(self, map_id: MapId) -> NewGameDraft:
        definition = self.map_library.load(map_id)
        return NewGameDraft(definition.id, definition.name, definition.default_starting_setup)

    def create_game(self, request: NewGameRequest) -> SessionView:
        map_draft = self.map_library.load_draft(request.map_id)
        definition = self.map_library.preview_definition(map_draft)
        validation = self.map_library.validate_starting_setup(definition, request.starting_setup)
        if not validation.is_valid:
            raise RepositoryError(
                "Starting setup is invalid: "
                + "; ".join(item.issue.message for item in validation.issues)
            )
        game = self.repository.create(
            CreateStoredGame(
                request.name,
                request.location,
                map_draft,
                request.starting_setup,
                request.settings,
            )
        )
        self._game = game
        self._phase = self.repository.load_phase(game.game_id, game.current_phase)
        self._perspective = GAMEMASTER
        return self._session()

    def select_phase(self, phase_id: PhaseId) -> SessionView:
        game, _ = self._require_game()
        if phase_id not in game.phases:
            raise RepositoryError(f"Phase is not in this game's history: {phase_id.label}")
        self._phase = self.repository.load_phase(game.game_id, phase_id)
        return self._session()

    def select_perspective(self, perspective: Perspective) -> SessionView:
        game, _ = self._require_game()
        if perspective.power_id is not None and perspective.power_id not in {
            power.id for power in game.map_definition.powers
        }:
            raise RepositoryError(f"Unknown perspective power: {perspective.power_id}")
        self._perspective = perspective
        return self._session()

    def _require_current(self) -> tuple[GameSnapshot, PhaseSnapshot]:
        game, phase = self._require_game()
        if phase.phase_id != game.current_phase:
            raise RepositoryError("Historical phases are read-only")
        return game, phase

    def update_orders(self, power_id, raw_text: str) -> PhaseSnapshot:
        game, phase = self._require_current()
        fresh = self.repository.load_phase(game.game_id, phase.phase_id)
        submission = self.order_processor.prepare_submission(
            game.map_definition, fresh, power_id, raw_text
        )
        updated = self.repository.save_submission(
            game.game_id, fresh.phase_id, submission, fresh.revision
        )
        self._phase = updated
        self._game = self.repository.open(game.location)
        return updated

    def set_orders_final(self, power_id, is_final: bool) -> PhaseSnapshot:
        """Set one power's finalisation state when the game tracks it.

        :param power_id: Power whose current submission state is changing.
        :param is_final: Whether the power has declared its orders final.
        :return: Updated current-phase snapshot.
        :raises RepositoryError: If finalisation is disabled or the phase is historical.
        """
        game, phase = self._require_current()
        if not game.settings.require_order_finalisation:
            raise RepositoryError("Order finalisation is not enabled for this game")
        fresh = self.repository.load_phase(game.game_id, phase.phase_id)
        updated = self.repository.set_final(
            game.game_id, fresh.phase_id, power_id, is_final, fresh.revision
        )
        self._phase = updated
        self._game = self.repository.open(game.location)
        return updated

    def resolve_and_advance(self, allow_unfinalised: bool = False) -> ResolveResult:
        """Adjudicate the current phase, optionally overriding enabled finalisation.

        :param allow_unfinalised: Whether to proceed past an enabled finalisation warning.
        :return: Either the advanced session or powers still awaiting finalisation.
        """
        game, phase = self._require_current()
        fresh = self.repository.load_phase(game.game_id, phase.phase_id)
        requirements = self.rules_engine.describe_phase(
            game.map_definition,
            fresh.phase_id,
            fresh.resolution_state or fresh.state,
        )
        unfinalised = (
            tuple(
                power.id
                for power in game.map_definition.powers
                if requirements.by_power[power.id].requires_submission
                and not (fresh.submissions.get(power.id) and fresh.submissions[power.id].is_final)
            )
            if game.settings.require_order_finalisation
            else ()
        )
        if unfinalised and not allow_unfinalised:
            return FinalisationRequired(unfinalised)
        proposal = self.rules_engine.adjudicate(game.map_definition, fresh)
        committed = self.repository.commit_adjudication(game.game_id, proposal, fresh.revision)
        self._game = committed
        self._phase = self.repository.load_phase(committed.game_id, committed.current_phase)
        return AdvancedPhase(self._session())

    def _projection(self, request: RenderRequest):
        game, phase = self._require_game()
        effective = self.rules_engine.effective_orders(game.map_definition, phase)
        overlay_orders: tuple[EffectiveOrder, ...] = ()
        overlay_results: tuple[OrderResult, ...] = ()
        retreat_phase = phase.phase_id.season in {Season.SUMMER, Season.WINTER}
        if retreat_phase:
            phase_index = game.phases.index(phase.phase_id)
            if phase_index:
                previous = self.repository.load_phase(game.game_id, game.phases[phase_index - 1])
                overlay_orders = self.rules_engine.effective_orders(game.map_definition, previous)
                overlay_results = previous.results
        return game, self.projector.project(
            game.map_definition,
            phase,
            effective,
            game.settings.visibility_policy,
            ProjectionRequest(
                self._perspective,
                request.label_mode,
                request.display_mode is DisplayMode.ORDERS or retreat_phase,
                game.settings.explain_adjudication_outcomes,
                request.show_only_successful_movements,
            ),
            overlay_orders,
            overlay_results,
        )

    def compose_map(self, request: RenderRequest) -> MapScene:
        game, projection = self._projection(request)
        return self.renderer.compose(game.map_definition, projection, request)

    def export_map(self, request: RenderRequest):
        scene = self.compose_map(request)
        return self.renderer.export(scene, request)

    def save_view(self, view: SavedView) -> GameSnapshot:
        game, _ = self._require_game()
        fresh = self.repository.open(game.location)
        updated = self.repository.save_view(game.game_id, view, fresh.revision)
        self._game = updated
        return updated

    def delete_view(self, view_id: SavedViewId) -> GameSnapshot:
        game, _ = self._require_game()
        fresh = self.repository.open(game.location)
        updated = self.repository.delete_view(game.game_id, view_id, fresh.revision)
        self._game = updated
        return updated

    def begin_game_map_edit(self) -> MapDraft:
        """Open the current game's complete private map source for editing.

        :return: Complete private map draft.
        :raises RepositoryError: If no game is open.
        """
        game, _ = self._require_game()
        return self.repository.load_map_draft(game.game_id)

    def save_game_map_draft(self, draft: MapDraft) -> SessionView:
        """Save a complete private game map and revalidate every saved submission.

        :param draft: Edited private map draft.
        :return: Refreshed game session.
        :raises RepositoryError: If the map ID changes or validation fails.
        """
        game, phase = self._require_game()
        if draft.map_id != game.map_definition.id:
            raise RepositoryError("A game's private map ID cannot be changed")
        validation = self.map_library.validate(draft)
        if not validation.is_valid:
            raise RepositoryError(
                "Game map has validation errors: "
                + "; ".join(item.issue.message for item in validation.issues)
            )
        definition = self.map_library.preview_definition(draft)
        revalidated: dict[PhaseId, dict[PowerId, OrderSubmission]] = {}
        for phase_id in game.phases:
            stored_phase = self.repository.load_phase(game.game_id, phase_id)
            if stored_phase.submissions:
                revalidated[phase_id] = {
                    power_id: self.order_processor.revalidate_submission(
                        definition,
                        stored_phase,
                        submission,
                    )
                    for power_id, submission in stored_phase.submissions.items()
                }
        updated = self.repository.save_map_draft(
            game.game_id,
            draft,
            revalidated,
            game.revision,
        )
        self._game = updated
        self._phase = self.repository.load_phase(updated.game_id, phase.phase_id)
        return self._session()

    def promote_game_map(
        self,
        draft: MapDraft,
        map_id: MapId,
        name: str,
    ) -> MapDefinition:
        """Copy a private game map into the canonical reusable library.

        :param draft: Private game-map draft whose design should be copied.
        :param map_id: Destination reusable-map identifier.
        :param name: Destination reusable-map name.
        :return: Saved canonical map definition.
        :raises RepositoryError: If the private map identity no longer matches the game.
        :raises MapLibraryError: If a requested new map ID already exists.
        """
        game, _ = self._require_game()
        if draft.map_id != game.map_definition.id:
            raise RepositoryError("A game's private map ID cannot be changed")
        existing = {summary.map_id for summary in self.map_library.list()}
        if map_id != draft.map_id and map_id in existing:
            raise MapLibraryError(f"Configured map already exists: {map_id}")
        canonical = self.map_library.load(draft.map_id)
        reusable = self.map_library.prepare_copy(
            draft,
            map_id,
            name,
            canonical.default_starting_setup,
        )
        return self.map_library.save(reusable)

    def list_maps(self) -> tuple[MapSummary, ...]:
        return self.map_library.list()

    def begin_map_import(self, name: str, svg: bytes) -> MapDraft:
        return self.map_library.import_svg(name, svg)

    def validate_map_draft(self, draft: MapDraft) -> MapValidation:
        return self.map_library.validate(draft)

    def load_map_draft(self, map_id: MapId) -> MapDraft:
        return self.map_library.load_draft(map_id)

    def refresh_map_draft(self, draft: MapDraft) -> MapDraft:
        return self.map_library.refresh_draft(draft)

    def preview_map_definition(self, draft: MapDraft) -> MapDefinition:
        return self.map_library.preview_definition(draft)

    def preview_map_base(self, draft: MapDraft) -> bytes:
        return self.renderer.base_map_svg(self.map_library.preview_definition(draft))

    def preview_map_setup(self, draft: MapDraft) -> MapScene:
        """Render a draft's starting position through the gameplay renderer.

        :param draft: Map draft whose configured starting position should be rendered.
        :return: Composed scene using the same path as the in-game position view.
        """
        definition = self.map_library.preview_definition(draft)
        state = definition.default_starting_setup.state
        units = {unit.location.territory_id: unit for unit in state.units}
        dislodged = {unit.unit.location.territory_id: unit.unit for unit in state.dislodged_units}
        projection = ProjectedMapState(
            definition.default_starting_setup.phase_id,
            GAMEMASTER,
            tuple(
                VisibleTerritory(
                    territory.id,
                    territory.display_name,
                    state.territory_controllers.get(territory.id),
                    state.supply_centre_owners.get(territory.id),
                    units.get(territory.id),
                    dislodged.get(territory.id),
                )
                for territory in definition.territories
            ),
            (),
            (),
        )
        request = RenderRequest(
            DisplayMode.POSITION,
            LabelMode.FULL_NAME,
            MapBounds(0, 0, 1, 1),
            PixelSize(1, 1),
        )
        return self.renderer.compose(definition, projection, request)

    def update_map_anchor(
        self, draft: MapDraft, territory_id, anchor, point, coast_id=None
    ) -> MapDraft:
        return self.map_library.update_anchor(draft, territory_id, anchor, point, coast_id)

    def update_map_coast_label_rotation(
        self, draft: MapDraft, territory_id, coast_id, rotation
    ) -> MapDraft:
        return self.map_library.update_coast_label_rotation(draft, territory_id, coast_id, rotation)

    def update_map_element_role(self, draft: MapDraft, element_id, role) -> MapDraft:
        return self.map_library.update_element_role(draft, element_id, role)

    def update_map_territory_name(self, draft: MapDraft, territory_id, name) -> MapDraft:
        return self.map_library.update_territory_name(draft, territory_id, name)

    def update_map_territory_display_name(
        self, draft: MapDraft, territory_id, display_name
    ) -> MapDraft:
        return self.map_library.update_territory_display_name(draft, territory_id, display_name)

    def update_map_territory_details(
        self, draft: MapDraft, territory_id, name, display_name, abbreviation
    ) -> MapDraft:
        """Update every editable user-facing name for one territory.

        :param draft: Authored map draft to update.
        :param territory_id: Stable territory whose names should change.
        :param name: Canonical name accepted by order entry.
        :param display_name: Potentially multiline rendered label.
        :param abbreviation: Unique three-letter order abbreviation.
        :return: Recompiled draft containing the updated territory.
        """
        return self.map_library.update_territory_details(
            draft, territory_id, name, display_name, abbreviation
        )

    def update_map_setup(self, draft: MapDraft, powers, starting_setup) -> MapDraft:
        """Update powers and the reusable starting state in one compilation.

        :param draft: Authored map draft to update.
        :param powers: Complete ordered power definitions.
        :param starting_setup: Complete starting phase and state.
        :return: Recompiled draft containing the updated setup.
        """
        return self.map_library.update_setup(draft, powers, starting_setup)

    def update_map_label_font_sizes(self, draft: MapDraft, territory_size, coast_size) -> MapDraft:
        return self.map_library.update_label_font_sizes(draft, territory_size, coast_size)

    def update_map_hold_offsets(
        self, draft: MapDraft, army_offset: Point, fleet_offset: Point
    ) -> MapDraft:
        """Update map-wide hold-underline offsets for armies and fleets."""
        return self.map_library.update_hold_offsets(draft, army_offset, fleet_offset)

    def update_map_colours(
        self, draft: MapDraft, label_colour, inaccessible_colour, sea_colour, unclaimed_colour
    ) -> MapDraft:
        return self.map_library.update_map_colours(
            draft, label_colour, inaccessible_colour, sea_colour, unclaimed_colour
        )

    def save_map_draft(self, draft: MapDraft) -> MapDefinition:
        return self.map_library.save(draft)
