from __future__ import annotations

import pytest
import yaml

from diplomacy_app.application.service import ApplicationService
from diplomacy_app.domain.errors import RepositoryError, RevisionConflict
from diplomacy_app.domain.models import (
    AdvancedPhase,
    CreateStoredGame,
    FinalisationRequired,
    GameLocation,
    GameSettings,
    NewGameRequest,
    OrderSubmission,
    Point,
)
from diplomacy_app.game_repository import FileGameRepository
from diplomacy_app.game_repository.recent_games import RecentGameStore
from diplomacy_app.map_library import FileMapLibrary
from diplomacy_app.map_library.defaults import DEFAULT_ARMY_SVG, DEFAULT_FLEET_SVG
from diplomacy_app.rendering import MapRenderer
from diplomacy_app.rules_engine import StandardRulesEngine
from diplomacy_app.visibility import VisibilityProjector


def repository(tmp_path):
    return FileGameRepository(RecentGameStore(tmp_path / "application.json"))


def test_game_folder_round_trip_revision_conflict_and_advance(tmp_path, england):
    repo = repository(tmp_path)
    location = GameLocation((tmp_path / "portable-game").resolve())
    game = repo.create(
        CreateStoredGame("Portable game", location, england, england.default_starting_setup)
    )
    config_path = location.path / "game.yaml"
    legacy_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    legacy_config.pop("orders")
    config_path.write_text(
        yaml.safe_dump(legacy_config, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    game = repo.open(location)
    assert not game.settings.require_order_finalisation
    phase = repo.load_phase(game.game_id, game.current_phase)
    updated = repo.save_submission(
        game.game_id,
        phase.phase_id,
        OrderSubmission(england.powers[0].id, "", (), False),
        phase.revision,
    )
    with pytest.raises(RevisionConflict):
        repo.save_submission(
            game.game_id,
            phase.phase_id,
            OrderSubmission(england.powers[1].id, "", (), False),
            phase.revision,
        )
    proposal = StandardRulesEngine().adjudicate(england, updated)
    advanced = repo.commit_adjudication(game.game_id, proposal, updated.revision)
    assert advanced.current_phase.label == "Fall 2000"
    (location.path / "map" / "army.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 100"><rect width="20" height="100"/></svg>',
        encoding="utf-8",
    )
    (location.path / "map" / "fleet.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 100"><rect width="20" height="100"/></svg>',
        encoding="utf-8",
    )
    reopened = repo.open(location)
    assert reopened.current_phase == advanced.current_phase
    assert (location.path / "map" / "_compiled-map.json").is_file()
    assert (location.path / "2000" / "Spring" / "orders.json").is_file()
    assert (location.path / "2000" / "Fall" / "state.json").is_file()
    assert reopened.map_definition.assets.army_svg == DEFAULT_ARMY_SVG
    assert reopened.map_definition.assets.fleet_svg == DEFAULT_FLEET_SVG


def test_coordinator_complete_default_order_workflow(tmp_path, project_root):
    maps = FileMapLibrary(tmp_path / "user-maps", project_root / "maps")
    repo = repository(tmp_path)
    service = ApplicationService(
        repo,
        maps,
        StandardRulesEngine(),
        VisibilityProjector(),
        MapRenderer(),
    )
    draft = service.prepare_new_game(maps.list()[0].map_id)
    session = service.create_game(
        NewGameRequest(
            "Coordinator game",
            GameLocation((tmp_path / "coordinator-game").resolve()),
            draft.map_id,
            draft.starting_setup,
            GameSettings(require_order_finalisation=True),
        )
    )
    blocked = service.resolve_and_advance()
    assert isinstance(blocked, FinalisationRequired)
    for power in session.game.map_definition.powers:
        service.set_orders_final(power.id, True)
    result = service.resolve_and_advance()
    assert isinstance(result, AdvancedPhase)
    assert result.session.phase.phase_id.label == "Fall 2000"
    assert service.start().game.name == "Coordinator game"

    untracked = service.create_game(
        NewGameRequest(
            "Untracked game",
            GameLocation((tmp_path / "untracked-game").resolve()),
            draft.map_id,
            draft.starting_setup,
        )
    )
    assert not untracked.game.settings.require_order_finalisation
    with pytest.raises(RepositoryError, match="not enabled"):
        service.set_orders_final(untracked.game.map_definition.powers[0].id, True)
    untracked_result = service.resolve_and_advance()
    assert isinstance(untracked_result, AdvancedPhase)
    assert untracked_result.session.phase.phase_id.label == "Fall 2000"


def test_coordinator_deletes_recent_and_current_games(tmp_path, project_root):
    maps = FileMapLibrary(tmp_path / "user-maps", project_root / "maps")
    repo = repository(tmp_path)
    service = ApplicationService(
        repo,
        maps,
        StandardRulesEngine(),
        VisibilityProjector(),
        MapRenderer(),
    )
    configured = maps.load(maps.list()[0].map_id)
    first_location = GameLocation((tmp_path / "first-game").resolve())
    second_location = GameLocation((tmp_path / "second-game").resolve())
    service.create_game(
        NewGameRequest(
            "First game",
            first_location,
            configured.id,
            configured.default_starting_setup,
        )
    )
    current = service.create_game(
        NewGameRequest(
            "Second game",
            second_location,
            configured.id,
            configured.default_starting_setup,
        )
    )

    after_first = service.delete_game(first_location)
    assert after_first.game == current.game
    assert not first_location.path.exists()
    assert [item.location for item in after_first.recent_games] == [second_location]
    assert repo.last_opened() == second_location

    after_current = service.delete_game(second_location)
    assert after_current.game is None
    assert after_current.phase is None
    assert after_current.recent_games == ()
    assert repo.last_opened() is None
    assert not second_location.path.exists()


def test_reusable_map_edit_does_not_change_existing_game_snapshot(tmp_path, project_root):
    maps = FileMapLibrary(tmp_path / "user-maps", project_root / "maps")
    configured = maps.load(maps.list()[0].map_id)
    game_location = GameLocation((tmp_path / "snapshot-game").resolve())
    repository(tmp_path).create(
        CreateStoredGame(
            "Snapshot game",
            game_location,
            configured,
            configured.default_starting_setup,
        )
    )
    private_yaml = game_location.path / "map" / "map.yaml"
    before = private_yaml.read_bytes()

    draft = maps.load_draft(configured.id)
    territory_id, old_point = next(iter(draft.presentation.label_anchors.items()))
    edited = maps.update_anchor(
        draft,
        territory_id,
        "label",
        Point(old_point.x + 7, old_point.y + 3),
    )
    maps.save(edited)

    assert private_yaml.read_bytes() == before
    assert maps.load(configured.id).presentation.label_anchors[territory_id] != old_point


def test_current_game_map_placement_changes_only_private_presentation(tmp_path, project_root):
    maps = FileMapLibrary(tmp_path / "user-maps", project_root / "maps")
    repo = repository(tmp_path)
    service = ApplicationService(
        repo,
        maps,
        StandardRulesEngine(),
        VisibilityProjector(),
        MapRenderer(),
    )
    configured = maps.load(maps.list()[0].map_id)
    location = GameLocation((tmp_path / "placement-game").resolve())
    original = service.create_game(
        NewGameRequest(
            "Placement game",
            location,
            configured.id,
            configured.default_starting_setup,
        )
    ).game.map_definition
    draft = service.begin_game_map_placement()
    territory_id, old_point = next(iter(draft.presentation.label_anchors.items()))
    moved_point = Point(old_point.x + 11, old_point.y - 4)
    edited = service.update_map_anchor(draft, territory_id, "label", moved_point)
    moved_abbreviation = Point(old_point.x - 6, old_point.y + 8)
    edited = service.update_map_anchor(edited, territory_id, "abbreviation", moved_abbreviation)
    edited = service.update_map_label_font_sizes(edited, 12.5, 8.5)
    edited = service.update_map_colours(edited, "#201810", "#303030", "#406080", "#d8c8a8")
    updated = service.save_game_map_placement(edited)

    reopened = repository(tmp_path).open(location)
    assert updated.game.map_definition.presentation.label_anchors[territory_id] == moved_point
    assert (
        updated.game.map_definition.presentation.abbreviation_anchors[territory_id]
        == moved_abbreviation
    )
    assert reopened.map_definition.presentation.label_anchors[territory_id] == moved_point
    assert reopened.map_definition.presentation.territory_label_font_size == 12.5
    assert reopened.map_definition.presentation.coast_label_font_size == 8.5
    assert reopened.map_definition.presentation.label_colour == "#201810"
    assert reopened.map_definition.presentation.inaccessible_region_colour == "#303030"
    assert reopened.map_definition.presentation.sea_colour == "#406080"
    assert reopened.map_definition.presentation.unclaimed_region_colour == "#d8c8a8"
    assert (
        reopened.map_definition.presentation.abbreviation_anchors[territory_id]
        == moved_abbreviation
    )
    assert reopened.map_definition.presentation.label_anchors[territory_id] != moved_abbreviation
    assert reopened.map_definition.territories == original.territories
    assert reopened.map_definition.adjacencies == original.adjacencies
    assert reopened.map_definition.powers == original.powers
    assert reopened.map_definition.default_starting_setup == original.default_starting_setup
    assert reopened.phases == updated.game.phases
    assert maps.load(configured.id).presentation.label_anchors[territory_id] == old_point
    assert maps.load(configured.id).presentation.abbreviation_anchors[territory_id] == old_point
    assert maps.load(configured.id).presentation.territory_label_font_size != 12.5
    assert maps.load(configured.id).presentation.sea_colour != "#406080"
