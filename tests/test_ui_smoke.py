from __future__ import annotations

from xml.etree import ElementTree

import pytest
import yaml
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import (
    QInputDevice,
    QKeySequence,
    QNativeGestureEvent,
    QPalette,
    QPointingDevice,
    QTextCursor,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsItem,
    QGraphicsView,
    QLabel,
    QPushButton,
)

from diplomacy_app.application.service import ApplicationService
from diplomacy_app.domain.models import (
    DisplayMode,
    GameLocation,
    LabelMode,
    MapBounds,
    NewGameRequest,
    PixelSize,
    Point,
    SavedView,
    SavedViewId,
)
from diplomacy_app.game_repository import FileGameRepository
from diplomacy_app.game_repository.recent_games import RecentGameStore
from diplomacy_app.map_library import FileMapLibrary
from diplomacy_app.rendering import MapRenderer
from diplomacy_app.rules_engine import StandardRulesEngine
from diplomacy_app.ui.application_window import ApplicationWindow, _quit_on_interrupt
from diplomacy_app.ui.map_canvas import (
    MapCanvas,
    SupplyCentreAnchorItem,
    TextAnchorItem,
    UnitAnchorItem,
)
from diplomacy_app.ui.map_manager_workspace import MapManagerWorkspace
from diplomacy_app.ui.map_wizard import MapWizard
from diplomacy_app.ui.style import STYLE, light_palette
from diplomacy_app.visibility import VisibilityProjector


def test_main_window_and_existing_map_wizard_construct(qtbot, tmp_path, project_root):
    app = QApplication.instance()
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setStyleSheet(STYLE)
    assert "QComboBox QAbstractItemView::item:selected" in STYLE
    assert "selection-color: #fffdf5" in STYLE
    assert "QPushButton, QToolButton { padding: 5px 9px; }" in STYLE
    assert "background: #fffdf7; color: #171714" in STYLE
    assert "QPlainTextEdit#setupEditor" in STYLE
    assert "QComboBox::down-arrow" in STYLE
    assert "border-top: 6px solid #39372f" in STYLE
    assert "QScrollBar::handle" in STYLE
    assert "Segoe UI" not in STYLE
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
    assert window.windowState() & Qt.WindowState.WindowMaximized
    assert set(window.close_window_action.shortcuts()) == set(
        QKeySequence.keyBindings(QKeySequence.StandardKey.Close)
    )
    assert window.tabs.objectName() == "primaryWorkspaceTabs"
    assert tuple(window.tabs.tabText(index) for index in range(window.tabs.count())) == (
        "Map",
        "Orders",
    )
    assert "tab:selected" in window.tabs.styleSheet()
    assert "background: #fffaf0; color: #20352b" in window.tabs.styleSheet()
    window.set_session(service.start())
    assert window.stack.currentWidget() is window.welcome
    assert not any(
        "Open a self-contained game folder" in label.text()
        for label in window.welcome.findChildren(QLabel)
    )
    assert window.map_workspace.zoom_controls.parent() is window.map_workspace.canvas
    assert window.map_workspace.zoom_controls.zoom_out.text() == "−"
    assert window.map_workspace.zoom_controls.zoom_in.text() == "+"
    assert window.map_workspace.outer_layout.contentsMargins().left() == 4
    assert window.map_workspace.fog_badge.parent() is window.map_workspace.canvas
    assert window.map_workspace.outcomes.parent() is window.map_workspace.canvas
    assert window.map_workspace.canvas.frameShape() is QFrame.Shape.NoFrame
    assert window.map_workspace.views.minimumWidth() == 240
    assert window.map_workspace.views.minimumContentsLength() == 26
    assert (
        window.map_workspace.views.sizeAdjustPolicy()
        is QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )
    window.map_workspace.mode.setCurrentIndex(1)
    window.map_workspace.labels.setCurrentIndex(1)
    render_request = window.map_workspace._request()
    assert render_request.display_mode is DisplayMode.ORDERS
    assert render_request.label_mode is LabelMode.ABBREVIATION
    window.show()
    QApplication.processEvents()
    control_palette = window.map_workspace.views.palette()
    assert control_palette.color(QPalette.ColorRole.Button).name() == "#fffaf0"
    assert control_palette.color(QPalette.ColorRole.ButtonText).name() == "#292820"
    assert window.statusBar().isHidden()

    wizard = MapWizard(service, service.load_map_draft(maps.list()[0].map_id))
    qtbot.addWidget(wizard)
    wizard.resize(1400, 900)
    wizard.show()
    QApplication.processEvents()
    for index in range(wizard.tabs.count()):
        page = wizard.tabs.widget(index)
        assert page.palette().color(QPalette.ColorRole.WindowText).name() == "#292820"
    assert wizard.yaml_editor.palette().color(QPalette.ColorRole.Text).name() == "#171714"
    assert wizard.setup_editor.palette().color(QPalette.ColorRole.Text).name() == "#171714"
    default_fit_canvas = MapCanvas()
    qtbot.addWidget(default_fit_canvas)
    default_fit_canvas.resize(320, 240)
    default_fit_canvas.set_svg(wizard.draft.svg)
    assert default_fit_canvas.transform().m11() < 1
    assert (
        wizard.anchor_canvas.viewportUpdateMode()
        is QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate
    )
    assert wizard.roles.rowCount() >= 74
    assert wizard.tabs.count() == 5
    assert tuple(wizard.tabs.tabText(index) for index in range(wizard.tabs.count())) == (
        "SVG regions",
        "Topology",
        "Powers and setup",
        "Placement",
        "Unit symbols",
    )
    assert wizard.validation_label.text().startswith("Valid:")
    assert wizard.outer_layout.contentsMargins().left() == 4
    assert wizard.tabs.widget(3).layout().contentsMargins().left() == 2
    assert wizard.placement_layers_group.title() == "Preview layers"
    assert wizard.placement_labels_group.title() == "Territory labels"
    assert wizard.label_sizes_group.title() == "Label sizes"
    assert wizard.map_colours_group.title() == "Map colours"
    assert wizard.tabs.widget(2).isAncestorOf(wizard.map_colours_group)
    assert wizard.display_name_group.title() == "Selected territory display name"
    assert wizard.coast_label_group.title() == "Selected coast label"
    assert wizard.placement_labels.minimumWidth() == 150
    assert wizard.territory_font_size.singleStep() == 0.5
    assert wizard.coast_font_size.singleStep() == 0.5
    assert wizard.coast_rotation.minimumWidth() == 90
    assert wizard.yaml_editor.textCursor().selectedText() == "territories:"
    assert wizard.yaml_find.find_shortcut.key() in QKeySequence.keyBindings(
        QKeySequence.StandardKey.Find
    )
    wizard.tabs.setCurrentIndex(1)
    wizard.yaml_find.show_find()
    wizard.yaml_find.query.setText("split_coasts:")
    assert wizard.yaml_editor.textCursor().selectedText() == "split_coasts:"
    wizard.yaml_find.close_find()
    assert wizard.yaml_find.isHidden()
    wizard.tabs.setCurrentIndex(2)
    assert wizard.setup_editor.objectName() == "setupEditor"
    wizard.setup_find.show_find()
    wizard.setup_find.query.setText("teams:")
    assert wizard.setup_editor.textCursor().selectedText() == "teams:"
    wizard.setup_find.close_find()
    assert wizard.save_button.text() == "Save configured map"
    for index in range(wizard.tabs.count()):
        wizard.tabs.setCurrentIndex(index)
        assert wizard.save_button.isEnabled()
    wizard.tabs.setCurrentIndex(1)
    wizard.yaml_editor.appendPlainText("\n# Retained when changing tabs")
    assert wizard.yaml_editor.document().isModified()
    wizard.tabs.setCurrentIndex(2)
    assert "# Retained when changing tabs" in wizard.draft.map_yaml
    assert not wizard.yaml_editor.document().isModified()
    setup = yaml.safe_load(wizard.setup_editor.toPlainText())
    power_id = next(iter(setup["teams"]))
    setup["teams"][power_id]["colour"] = "#123456"
    wizard.setup_editor.setPlainText(yaml.safe_dump(setup, sort_keys=False))
    wizard.setup_editor.document().setModified(True)
    wizard.tabs.setCurrentIndex(3)
    assert yaml.safe_load(wizard.draft.map_yaml)["teams"][power_id]["colour"] == "#123456"
    assert wizard.setup_validation_label.text() == "Map preview regenerated"
    assert wizard.setup_canvas._renderer is not None
    assert wizard.setup_canvas._renderer.isValid()
    setup_preview = ElementTree.fromstring(service.preview_map_setup(wizard.draft).svg)
    recoloured = next(
        node
        for node in setup_preview.iter()
        if node.attrib.get("id")
        == next(
            territory.svg_element_id
            for territory in wizard.draft.territories
            if wizard.draft.default_starting_setup.state.territory_controllers.get(territory.id)
            == power_id
        )
    )
    assert recoloured.attrib["style"] == "fill:#123456"
    assert not any(
        button.text() == "Reload anchors from YAML" for button in wizard.findChildren(QPushButton)
    )
    definition = service.preview_map_definition(wizard.draft)
    topology = ElementTree.fromstring(wizard._topology_svg(definition))
    topology_nodes = {
        node.attrib["data-location"]: node
        for node in topology.findall(".//{*}circle")
        if "data-territory" in node.attrib
    }
    underlay = next(
        group
        for group in topology.findall(".//{*}g")
        if group.attrib.get("id") == "topology-map-underlay"
    )
    graph_edges = [line for line in topology.findall(".//{*}line") if "data-kind" in line.attrib]
    node_layer = next(
        group for group in topology.findall(".//{*}g") if group.attrib.get("id") == "topology-nodes"
    )
    topology_coast_labels = next(
        group for group in underlay.findall(".//{*}g") if group.attrib.get("id") == "coast-labels"
    )
    assert underlay.attrib["opacity"] == "0.58"
    assert graph_edges
    wizard.tabs.setCurrentIndex(1)
    QApplication.processEvents()
    yaml_width, map_width = wizard.topology_splitter.sizes()
    assert map_width >= yaml_width * 2
    assert wizard.topology_splitter.handleWidth() == 2
    wizard.tabs.setCurrentIndex(3)
    assert {label.attrib["font-size"] for label in node_layer.findall("{*}text")} == {"11"}
    assert {label.attrib["fill"] for label in node_layer.findall("{*}text")} == {"#111111"}
    assert all("stroke" not in label.attrib for label in node_layer.findall("{*}text"))
    assert {label.text for label in topology_coast_labels.findall("{*}text")} >= {
        "North Coast",
        "South Coast",
    }
    assert {label.attrib["font-size"] for label in topology_coast_labels.findall("{*}text")} == {
        "9"
    }
    assert {label.attrib["fill"] for label in topology_coast_labels.findall("{*}text")} == {
        definition.presentation.label_colour
    }
    assert {location for location in topology_nodes if location.startswith("devon")} == {
        "devon",
        "devon/north",
        "devon/south",
    }
    assert {
        topology_nodes[location].attrib["data-anchor-type"]
        for location in topology_nodes
        if location.startswith("devon/")
    } == {"fleet"}
    assert any(
        line.attrib.get("data-origin", "").startswith("devon/")
        or line.attrib.get("data-destination", "").startswith("devon/")
        for line in graph_edges
    )
    devon = next(item for item in definition.territories if str(item.id) == "devon")
    devon_point = definition.presentation.army_anchors[devon.id]
    wizard._topology_hovered(devon_point.x, devon_point.y)
    topology_yaml_highlights = wizard.yaml_editor.extraSelections()
    assert len(topology_yaml_highlights) == 1
    assert "split_coasts:" in topology_yaml_highlights[0].cursor.selectedText()
    assert wizard.yaml_editor.textCursor().block().text().strip() == "devon:"
    assert "Devon" in wizard.topology_canvas.toolTip()
    assert wizard.army_asset_preview.minimumWidth() == 420
    assert wizard.army_asset_preview.minimumHeight() == 320
    assert wizard.army_asset_preview.transform().m11() < 1.2
    assert wizard.fleet_asset_preview.transform().m11() < 1.2
    for canvas, unit_type in (
        (wizard.army_asset_preview, "army"),
        (wizard.fleet_asset_preview, "fleet"),
    ):
        symbol_items = [item for item in canvas.scene().items() if isinstance(item, UnitAnchorItem)]
        assert len(symbol_items) == len(
            [
                unit
                for unit in definition.default_starting_setup.state.units
                if unit.unit_type.value == unit_type
            ]
        )
        assert not symbol_items[0].flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        assert canvas._renderer.elementExists("territory-labels")
    assert wizard.setup_canvas._renderer.elementExists("units")
    assert wizard.preview._renderer.elementExists("gamemaster-layers")
    multiline_label = TextAnchorItem(
        Point(0, 0), "Derbyshire & Nottinghamshire", "#111111", lambda _point: None
    )
    assert multiline_label.glyph.toPlainText() == "Derbyshire &\nNottinghamshire"
    land = next(item for item in definition.territories if item.kind.value == "land")
    sea = next(item for item in definition.territories if item.kind.value == "sea")
    land_node = topology_nodes[str(land.id)]
    sea_node = topology_nodes[str(sea.id)]
    assert land_node.attrib["data-anchor-type"] == "army"
    assert float(land_node.attrib["cx"]) == definition.presentation.army_anchors[land.id].x
    assert float(land_node.attrib["cy"]) == definition.presentation.army_anchors[land.id].y
    assert sea_node.attrib["data-anchor-type"] == "fleet"
    assert (
        float(sea_node.attrib["cx"])
        == definition.presentation.fleet_anchors[
            next(
                location
                for location in definition.presentation.fleet_anchors
                if location.territory_id == sea.id
            )
        ].x
    )
    assert (
        float(sea_node.attrib["cy"])
        == definition.presentation.fleet_anchors[
            next(
                location
                for location in definition.presentation.fleet_anchors
                if location.territory_id == sea.id
            )
        ].y
    )
    wizard.anchor_canvas.fit_map()
    QApplication.processEvents()
    assert not wizard.anchor_canvas.horizontalScrollBar().isVisible()
    assert not wizard.anchor_canvas.verticalScrollBar().isVisible()
    fitted_control_position = wizard.placement_zoom.pos()
    initial_zoom = wizard.anchor_canvas.transform().m11()
    wizard.placement_zoom.zoom_in.click()
    QApplication.processEvents()
    assert wizard.anchor_canvas.transform().m11() > initial_zoom
    assert (
        wizard.anchor_canvas.horizontalScrollBar().isVisible()
        or wizard.anchor_canvas.verticalScrollBar().isVisible()
    )
    assert wizard.placement_zoom.pos() == fitted_control_position
    wizard.placement_zoom.percentage.setText("175%")
    wizard.placement_zoom.percentage.editingFinished.emit()
    assert wizard.anchor_canvas.transform().m11() == pytest.approx(1.75)
    assert wizard.placement_zoom.percentage.text() == "175%"
    assert wizard.placement_zoom.pos() == fitted_control_position
    wizard.placement_zoom.percentage.setText("not a percentage")
    wizard.placement_zoom.percentage.editingFinished.emit()
    assert wizard.placement_zoom.percentage.text() == "175%"
    zoomed_in = wizard.anchor_canvas.transform().m11()
    wizard.placement_zoom.zoom_out.click()
    assert wizard.anchor_canvas.transform().m11() < zoomed_in
    wizard.anchor_canvas.set_standard_zoom()
    before_scale = wizard.anchor_canvas.transform().m11()
    before_scroll = wizard.anchor_canvas.verticalScrollBar().value()
    touchpad = QPointingDevice(
        "Test trackpad",
        10_001,
        QInputDevice.DeviceType.TouchPad,
        QPointingDevice.PointerType.Finger,
        QInputDevice.Capability.Position | QInputDevice.Capability.PixelScroll,
        10,
        0,
    )
    trackpad_scroll = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        QPoint(0, -40),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
        Qt.MouseEventSource.MouseEventNotSynthesized,
        touchpad,
    )
    wizard.anchor_canvas.wheelEvent(trackpad_scroll)
    assert wizard.anchor_canvas.transform().m11() == before_scale
    assert wizard.anchor_canvas.verticalScrollBar().value() > before_scroll
    assert wizard.placement_zoom.y() == 8
    assert (
        wizard.placement_zoom.x()
        == wizard.anchor_canvas.width() - wizard.placement_zoom.width() - 12
    )
    anchored_position = wizard.placement_zoom.pos()
    mouse = QPointingDevice(
        "Test mouse",
        10_002,
        QInputDevice.DeviceType.Mouse,
        QPointingDevice.PointerType.Generic,
        QInputDevice.Capability.Position
        | QInputDevice.Capability.Scroll
        | QInputDevice.Capability.PixelScroll,
        1,
        3,
    )
    mouse_wheel = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        QPoint(0, 12),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
        Qt.MouseEventSource.MouseEventNotSynthesized,
        mouse,
    )
    wizard.anchor_canvas.wheelEvent(mouse_wheel)
    assert wizard.anchor_canvas.transform().m11() > before_scale
    assert wizard.placement_zoom.pos() == anchored_position
    assert wizard.anchor_canvas.verticalScrollBar().width() <= 8
    pinch_position = QPointF(
        wizard.anchor_canvas.viewport().width() / 2,
        wizard.anchor_canvas.viewport().height() / 2,
    )
    pinch_scene_position = wizard.anchor_canvas.mapToScene(pinch_position.toPoint())
    pointing_device = QPointingDevice.primaryPointingDevice()
    pinch = QNativeGestureEvent(
        Qt.NativeGestureType.ZoomNativeGesture,
        pointing_device,
        2,
        pinch_position,
        pinch_position,
        pinch_position,
        0.15,
        QPointF(),
        1,
    )
    before_pinch_scale = wizard.anchor_canvas.transform().m11()
    assert wizard.anchor_canvas.viewportEvent(pinch)
    assert wizard.anchor_canvas.transform().m11() > before_pinch_scale
    moved_scene_position = wizard.anchor_canvas.mapToScene(pinch_position.toPoint())
    assert moved_scene_position.x() == pytest.approx(pinch_scene_position.x())
    assert moved_scene_position.y() == pytest.approx(pinch_scene_position.y())
    for controls in (
        wizard.regions_zoom,
        wizard.topology_zoom,
        wizard.setup_zoom,
        wizard.placement_zoom,
        wizard.army_asset_zoom,
        wizard.fleet_asset_zoom,
    ):
        assert not controls.zoom_in.isHidden()
        assert not controls.zoom_out.isHidden()
        assert controls.parent() is controls.canvas
        assert controls.zoom_out.text() == "−"
        assert controls.zoom_in.text() == "+"
        assert controls.percentage.text() == f"{round(controls.canvas.transform().m11() * 100)}%"
        assert controls.y() == 8
    army_items = [
        item for item in wizard.anchor_canvas.scene().items() if isinstance(item, UnitAnchorItem)
    ]
    army_count = len(army_items)
    assert army_count == len(wizard.draft.presentation.army_anchors)
    assert all(len(item.childItems()) == 1 for item in army_items)
    assert all(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable for item in army_items)
    assert all(
        not item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable for item in army_items
    )
    assert all(
        len(item.childItems()) == 1
        for item in wizard.anchor_canvas.scene().items()
        if isinstance(item, TextAnchorItem)
    )
    centre_items = [
        item
        for item in wizard.anchor_canvas.scene().items()
        if isinstance(item, SupplyCentreAnchorItem)
    ]
    assert len(centre_items) == len(wizard.draft.presentation.supply_centre_anchors)
    assert all(len(item.childItems()) == 1 for item in centre_items)
    assert all(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable for item in centre_items)
    selectable_labels = [
        item
        for item in wizard.anchor_canvas.scene().items()
        if isinstance(item, TextAnchorItem)
        and item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
    ]
    selectable_coast_labels = [item for item in selectable_labels if item.glyph.font().italic()]
    selectable_territory_labels = [
        item for item in selectable_labels if not item.glyph.font().italic()
    ]
    assert len(selectable_coast_labels) == len(wizard.draft.presentation.coast_label_anchors)
    assert len(selectable_territory_labels) == len(wizard.draft.presentation.label_anchors)
    assert {
        label.glyph.font().pixelSize() * label.scale() for label in selectable_coast_labels
    } == {9.0}
    display_territory = wizard.draft.territories[0]
    canonical_name = display_territory.name
    wizard._select_territory_label(display_territory.id)
    wizard.display_name_editor.setPlainText("First display line")
    wizard.display_name_editor.moveCursor(QTextCursor.MoveOperation.End)
    qtbot.keyClick(
        wizard.display_name_editor,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.ShiftModifier,
    )
    qtbot.keyClicks(wizard.display_name_editor, "Second display line")
    qtbot.keyClick(wizard.display_name_editor, Qt.Key.Key_Return)
    updated_territory = next(
        item for item in wizard.draft.territories if item.id == display_territory.id
    )
    assert updated_territory.name == canonical_name
    assert updated_territory.display_name == "First display line\nSecond display line"
    assert (
        yaml.safe_load(wizard.draft.map_yaml)["territories"][str(display_territory.id)][
            "display_name"
        ]
        == "First display line\nSecond display line"
    )
    wizard.territory_font_size.setValue(12.5)
    wizard.coast_font_size.setValue(8.5)
    assert wizard.draft.presentation.territory_label_font_size == 12.5
    assert wizard.draft.presentation.coast_label_font_size == 8.5
    resized_labels = [
        item for item in wizard.anchor_canvas.scene().items() if isinstance(item, TextAnchorItem)
    ]
    assert {
        item.glyph.font().pixelSize() * item.scale()
        for item in resized_labels
        if not item.glyph.font().italic()
    } == {12.5}
    assert {
        item.glyph.font().pixelSize() * item.scale()
        for item in resized_labels
        if item.glyph.font().italic()
    } == {8.5}
    wizard._set_map_colour("label_colour", "#201810")
    wizard._set_map_colour("inaccessible_region_colour", "#303030")
    wizard._set_map_colour("sea_colour", "#406080")
    wizard._set_map_colour("unclaimed_region_colour", "#d8c8a8")
    assert wizard.label_colour_button.text() == "Text #201810"
    assert wizard.inaccessible_colour_button.text() == "Inaccessible #303030"
    assert wizard.sea_colour_button.text() == "Sea #406080"
    assert wizard.unclaimed_colour_button.text() == "Unclaimed #D8C8A8"
    base_preview = ElementTree.fromstring(service.preview_map_base(wizard.draft))
    inaccessible_node = next(
        node for node in base_preview.iter() if node.attrib.get("id") == "impassable-scotland"
    )
    sea_territory = next(item for item in wizard.draft.territories if item.kind.value == "sea")
    sea_node = next(
        node
        for node in base_preview.iter()
        if node.attrib.get("id") == sea_territory.svg_element_id
    )
    land_territory = next(item for item in wizard.draft.territories if item.kind.value == "land")
    land_node = next(
        node
        for node in base_preview.iter()
        if node.attrib.get("id") == land_territory.svg_element_id
    )
    assert inaccessible_node.attrib["style"].endswith("fill:url(#gamemaster-inaccessible-stripes)")
    inaccessible_pattern = next(
        node
        for node in base_preview.iter()
        if node.attrib.get("id") == "gamemaster-inaccessible-stripes"
    )
    assert inaccessible_pattern.find("{*}rect").attrib["fill"] == "#303030"
    assert "patternTransform" not in inaccessible_pattern.attrib
    stripe = inaccessible_pattern.find("{*}path")
    assert stripe is not None
    assert stripe.attrib["d"].count("M") == 3
    assert sea_node.attrib["style"].endswith("fill:#406080")
    assert land_node.attrib["style"].endswith("fill:#d8c8a8")
    coast_location, coast_anchor = next(iter(wizard.draft.presentation.coast_label_anchors.items()))
    moved_coast_anchor = Point(coast_anchor.x + 2, coast_anchor.y + 3)
    wizard._anchor_moved(
        coast_location.territory_id,
        "coast_label",
        str(coast_location.coast_id),
        moved_coast_anchor,
    )
    assert wizard.draft.presentation.coast_label_anchors[coast_location] == moved_coast_anchor
    wizard._select_coast_label(coast_location)
    wizard.coast_rotation.setValue(25)
    assert wizard.draft.presentation.coast_label_rotations[coast_location] == 25
    assert wizard._coast_label_items[coast_location].rotation() == 25
    wizard.anchor_canvas.scene_pressed.emit()
    assert wizard._selected_coast_label is None
    assert not wizard.coast_rotation.isEnabled()
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
    assert any(isinstance(item, TextAnchorItem) for item in wizard.anchor_canvas.scene().items())
    wizard.coast_labels_preview.setChecked(False)
    assert not any(
        isinstance(item, TextAnchorItem) for item in wizard.anchor_canvas.scene().items()
    )
    territory = wizard.draft.territories[0]
    point = wizard._element_geometries[territory.svg_element_id].representative_point()
    wizard._map_hovered(point.x, point.y)
    assert territory.name in wizard.hovered_territory.text()
    assert wizard.roles.currentRow() == wizard._row_by_element[territory.svg_element_id]
    scotland_id = "impassable-scotland"
    scotland = wizard._element_geometries[scotland_id].representative_point()
    wizard._map_hovered(scotland.x, scotland.y)
    assert wizard.roles.currentRow() == wizard._row_by_element[scotland_id]
    assert "Scotland — Impassable" in wizard.hovered_territory.text()
    anchor_id, anchor_point = next(iter(wizard.draft.presentation.label_anchors.items()))
    moved_anchor = Point(anchor_point.x + 1, anchor_point.y + 1)
    wizard._anchor_moved(anchor_id, "label", None, moved_anchor)
    assert wizard.draft.presentation.label_anchors[anchor_id] == moved_anchor
    original_abbreviation_anchor = wizard.draft.presentation.abbreviation_anchors[anchor_id]
    moved_abbreviation_anchor = Point(anchor_point.x - 2, anchor_point.y + 3)
    wizard.placement_labels.setCurrentIndex(2)
    wizard._anchor_moved(
        anchor_id,
        "abbreviation",
        None,
        moved_abbreviation_anchor,
    )
    assert wizard.draft.presentation.abbreviation_anchors[anchor_id] == moved_abbreviation_anchor
    assert wizard.draft.presentation.label_anchors[anchor_id] == moved_anchor
    assert original_abbreviation_anchor != moved_abbreviation_anchor
    renamed_territory = wizard.draft.territories[0]
    renamed_row = wizard._row_by_element[renamed_territory.svg_element_id]
    wizard.roles.item(renamed_row, 0).setText("Persisted place name")
    assert (
        next(
            territory.name
            for territory in wizard.draft.territories
            if territory.id == renamed_territory.id
        )
        == "Persisted place name"
    )
    saved = []
    wizard.saved.connect(saved.append)
    wizard.tabs.setCurrentIndex(3)
    wizard.save_button.click()
    assert saved and saved[0].id == wizard.draft.map_id
    assert maps.load(saved[0].id).presentation.label_anchors[anchor_id] == moved_anchor
    assert (
        maps.load(saved[0].id).presentation.abbreviation_anchors[anchor_id]
        == moved_abbreviation_anchor
    )
    assert maps.load(saved[0].id).presentation.territory_label_font_size == 12.5
    assert maps.load(saved[0].id).presentation.coast_label_font_size == 8.5
    assert maps.load(saved[0].id).presentation.inaccessible_region_colour == "#303030"
    assert maps.load(saved[0].id).presentation.sea_colour == "#406080"
    assert maps.load(saved[0].id).presentation.unclaimed_region_colour == "#d8c8a8"
    reopened_maps = FileMapLibrary(tmp_path / "maps", project_root / "maps")
    assert (
        next(
            territory.name
            for territory in reopened_maps.load_draft(saved[0].id).territories
            if territory.id == renamed_territory.id
        )
        == "Persisted place name"
    )
    assert (
        next(
            territory.display_name
            for territory in reopened_maps.load_draft(saved[0].id).territories
            if territory.id == renamed_territory.id
        )
        == "First display line\nSecond display line"
    )

    manager = MapManagerWorkspace(service)
    qtbot.addWidget(manager)
    assert manager.map_selector.count() >= 1
    assert not any(
        "Import a structured SVG" in label.text() for label in manager.findChildren(QLabel)
    )

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
    window.show()
    assert window.isMaximized()
    window.close_window_action.trigger()
    assert not window.isVisible()


def test_terminal_interrupt_requests_normal_application_quit():
    class ApplicationProbe:
        quit_requested = False

        def quit(self):
            self.quit_requested = True

    app = ApplicationProbe()
    _quit_on_interrupt(app, 2, None)
    assert app.quit_requested


def test_current_game_opens_placement_only_editor(qtbot, tmp_path, project_root):
    maps = FileMapLibrary(tmp_path / "maps", project_root / "maps")
    service = ApplicationService(
        FileGameRepository(RecentGameStore(tmp_path / "app.json")),
        maps,
        StandardRulesEngine(),
        VisibilityProjector(),
        MapRenderer(),
    )
    configured = maps.load(maps.list()[0].map_id)
    session = service.create_game(
        NewGameRequest(
            "Placement UI game",
            GameLocation((tmp_path / "game").resolve()),
            configured.id,
            configured.default_starting_setup,
        )
    )
    window = ApplicationWindow(service)
    qtbot.addWidget(window)
    window.set_session(session, open_map=True)
    assert not window.game_map_placement_button.isHidden()
    assert window.tabs.currentIndex() == 0
    assert window.stack.currentWidget() is window.map_workspace
    window.tabs.setCurrentIndex(1)
    assert window.stack.currentWidget() is window.orders_workspace
    window.tabs.setCurrentIndex(0)
    assert window.stack.currentWidget() is window.map_workspace
    window.map_workspace.refresh()
    saved_view = SavedView(
        SavedViewId("close-up"),
        "Close-up of the western approaches",
        MapBounds(0, 0, 240, 240),
        1,
        PixelSize(800, 800),
    )
    window.map_workspace.views.addItem(saved_view.name, saved_view)
    window.map_workspace.views.setCurrentIndex(window.map_workspace.views.count() - 1)
    assert window.map_workspace.views.currentText() == saved_view.name
    window.map_workspace.canvas.zoom_by(1.2)
    assert window.map_workspace.views.currentText() == "Custom view"
    assert window.map_workspace.views.currentData() == "custom"
    window.map_workspace.views.setCurrentIndex(window.map_workspace.views.findData(saved_view))
    assert window.map_workspace.views.currentText() == saved_view.name
    scrollbars = (
        window.map_workspace.canvas.horizontalScrollBar(),
        window.map_workspace.canvas.verticalScrollBar(),
    )
    scrollbar = next(item for item in scrollbars if item.maximum() > item.minimum())
    target = (
        scrollbar.value() + 1 if scrollbar.value() < scrollbar.maximum() else scrollbar.value() - 1
    )
    scrollbar.setValue(target)
    assert window.map_workspace.views.currentText() == "Custom view"
    copy_errors = []
    window.map_workspace.message.connect(copy_errors.append)
    window.map_workspace._copy()
    assert not copy_errors
    assert not QApplication.clipboard().image().isNull()
    assert window.map_workspace.copy_button.text() == "Copied"

    window.game_map_placement_button.click()
    editor = window.stack.currentWidget()
    assert isinstance(editor, MapWizard)
    assert editor.game_placement_only
    assert editor.tabs.count() == 1
    assert editor.tabs.tabText(0) == "Placement"
    assert editor.save_button.text() == "Save game map placement"
    assert not hasattr(editor, "yaml_editor")

    territory_id, old_point = next(iter(editor.draft.presentation.label_anchors.items()))
    moved_point = Point(old_point.x + 3, old_point.y + 5)
    editor._anchor_moved(territory_id, "label", None, moved_point)
    editor.save_button.click()
    assert window.stack.currentWidget() is window.map_workspace
    assert (
        window.session.game.map_definition.presentation.label_anchors[territory_id] == moved_point
    )
