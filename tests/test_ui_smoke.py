from __future__ import annotations

from diplomacy_app.application.service import ApplicationService
from diplomacy_app.game_repository import FileGameRepository
from diplomacy_app.game_repository.recent_games import RecentGameStore
from diplomacy_app.map_library import FileMapLibrary
from diplomacy_app.rendering import MapRenderer
from diplomacy_app.rules_engine import StandardRulesEngine
from diplomacy_app.ui.application_window import ApplicationWindow
from diplomacy_app.ui.map_canvas import UnitAnchorItem
from diplomacy_app.ui.map_manager_dialog import MapManagerDialog
from diplomacy_app.ui.map_wizard import MapWizard
from diplomacy_app.visibility import VisibilityProjector


def test_main_window_and_existing_map_wizard_construct(qtbot, tmp_path, project_root):
    maps = FileMapLibrary(tmp_path / "maps", project_root / "maps")
    service = ApplicationService(
        FileGameRepository(RecentGameStore(tmp_path / "app.json")),
        maps,
        StandardRulesEngine(),
        VisibilityProjector(),
        MapRenderer(),
    )
    window = ApplicationWindow(service)
    qtbot.addWidget(window)
    window.set_session(service.start())
    assert window.stack.currentWidget() is window.welcome

    wizard = MapWizard(service, service.load_map_draft(maps.list()[0].map_id))
    qtbot.addWidget(wizard)
    assert wizard.roles.rowCount() >= 74
    assert wizard.tabs.count() == 4
    army_count = len(
        [item for item in wizard.anchor_canvas.scene().items() if isinstance(item, UnitAnchorItem)]
    )
    assert army_count == len(wizard.draft.presentation.army_anchors)
    wizard.fleets_preview.click()
    assert wizard.fleets_preview.isChecked()
    assert not wizard.armies_preview.isChecked()
    fleet_count = len(
        [item for item in wizard.anchor_canvas.scene().items() if isinstance(item, UnitAnchorItem)]
    )
    assert fleet_count == len(wizard.draft.presentation.fleet_anchors)

    manager = MapManagerDialog(service)
    qtbot.addWidget(manager)
    assert manager.map_selector.count() >= 1
