from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent

from diplomacy_app.application.service import ApplicationService
from diplomacy_app.game_repository import FileGameRepository
from diplomacy_app.game_repository.recent_games import RecentGameStore
from diplomacy_app.map_library import FileMapLibrary
from diplomacy_app.rendering import MapRenderer
from diplomacy_app.rules_engine import StandardRulesEngine
from diplomacy_app.ui.application_window import ApplicationWindow
from diplomacy_app.ui.map_canvas import TextAnchorItem, UnitAnchorItem
from diplomacy_app.ui.map_manager_workspace import MapManagerWorkspace
from diplomacy_app.ui.map_wizard import MapWizard
from diplomacy_app.ui.style import STYLE
from diplomacy_app.visibility import VisibilityProjector


def test_main_window_and_existing_map_wizard_construct(qtbot, tmp_path, project_root):
    assert "QComboBox QAbstractItemView::item:selected" in STYLE
    assert "selection-color: #fffdf5" in STYLE
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
    assert wizard.validation_label.text().startswith("Valid:")
    assert wizard.next_button.text() == "Next"
    initial_zoom = wizard.anchor_canvas.transform().m11()
    wizard.placement_zoom.zoom_in.click()
    assert wizard.anchor_canvas.transform().m11() > initial_zoom
    zoomed_in = wizard.anchor_canvas.transform().m11()
    wizard.placement_zoom.zoom_out.click()
    assert wizard.anchor_canvas.transform().m11() < zoomed_in
    wizard.anchor_canvas.set_standard_zoom()
    before_scale = wizard.anchor_canvas.transform().m11()
    before_scroll = wizard.anchor_canvas.verticalScrollBar().value()
    trackpad_scroll = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        QPoint(0, -40),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    wizard.anchor_canvas.wheelEvent(trackpad_scroll)
    assert wizard.anchor_canvas.transform().m11() == before_scale
    assert wizard.anchor_canvas.verticalScrollBar().value() > before_scroll
    mouse_wheel = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    wizard.anchor_canvas.wheelEvent(mouse_wheel)
    assert wizard.anchor_canvas.transform().m11() > before_scale
    for controls in (
        wizard.regions_zoom,
        wizard.topology_zoom,
        wizard.placement_zoom,
        wizard.army_asset_zoom,
        wizard.fleet_asset_zoom,
    ):
        assert not controls.zoom_in.isHidden()
        assert not controls.zoom_out.isHidden()
    army_count = len(
        [item for item in wizard.anchor_canvas.scene().items() if isinstance(item, UnitAnchorItem)]
    )
    assert army_count == len(wizard.draft.presentation.army_anchors)
    wizard.fleets_preview.click()
    assert wizard.fleets_preview.isChecked()
    assert wizard.armies_preview.isChecked()
    combined_count = len(
        [item for item in wizard.anchor_canvas.scene().items() if isinstance(item, UnitAnchorItem)]
    )
    assert combined_count == len(wizard.draft.presentation.army_anchors) + len(
        wizard.draft.presentation.fleet_anchors
    )
    wizard.armies_preview.click()
    wizard.fleets_preview.click()
    assert not wizard.armies_preview.isChecked()
    assert not wizard.fleets_preview.isChecked()
    assert not any(
        isinstance(item, UnitAnchorItem) for item in wizard.anchor_canvas.scene().items()
    )
    assert any(isinstance(item, TextAnchorItem) for item in wizard.anchor_canvas.scene().items())
    wizard.supply_preview.setChecked(False)
    wizard.placement_labels.setCurrentIndex(0)
    assert not any(
        isinstance(item, TextAnchorItem) for item in wizard.anchor_canvas.scene().items()
    )
    territory = wizard.draft.territories[0]
    point = wizard._territory_geometries[territory.svg_element_id].representative_point()
    wizard._map_hovered(point.x, point.y)
    assert territory.name in wizard.hovered_territory.text()
    assert wizard.roles.currentRow() == wizard._row_by_element[territory.svg_element_id]
    wizard.tabs.setCurrentIndex(3)
    assert wizard.next_button.text() == "Save configured map"

    manager = MapManagerWorkspace(service)
    qtbot.addWidget(manager)
    assert manager.map_selector.count() >= 1

    window._configure_maps()
    assert isinstance(window.stack.currentWidget(), MapManagerWorkspace)
    assert window.isWindow()
    manager_page = window.stack.currentWidget()
    manager_page._edit()
    embedded_wizard = window.stack.currentWidget()
    assert isinstance(embedded_wizard, MapWizard)
    assert not embedded_wizard.isWindow()
    embedded_wizard.cancelled.emit()
    assert window.stack.currentWidget() is manager_page
