from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

import pytest
import yaml
from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QFocusEvent, QKeySequence, QPalette, QTextCursor, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsItem,
    QGraphicsView,
    QLabel,
    QMessageBox,
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
from diplomacy_app.presentation import aspect_fitted_size
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
from diplomacy_app.ui.new_game_workspace import NewGameWorkspace
from diplomacy_app.ui.style import STYLE, light_palette
from diplomacy_app.visibility import VisibilityProjector


def test_new_game_uses_a_named_folder_below_the_selected_location(qtbot, tmp_path, configured_maps):
    games_location = tmp_path / "games"
    games_location.mkdir()
    maps = configured_maps
    service = ApplicationService(
        FileGameRepository(RecentGameStore(tmp_path / "app.json")),
        maps,
        StandardRulesEngine(),
        VisibilityProjector(),
        MapRenderer(),
    )
    workspace = NewGameWorkspace(service)
    qtbot.addWidget(workspace)

    workspace.name.setText("Friday Night Game")
    workspace.folder.setText(str(games_location))
    assert not workspace.order_finalisation.isChecked()
    workspace.order_finalisation.setChecked(True)

    expected = games_location / "friday-night-game"
    assert workspace.destination.text() == str(expected)

    workspace._create()

    assert workspace.created_session is not None
    assert workspace.created_session.game.game_id == "friday-night-game"
    assert workspace.created_session.game.location.path == expected
    assert workspace.created_session.game.settings.require_order_finalisation
    assert yaml.safe_load((expected / "game.yaml").read_text(encoding="utf-8"))["orders"] == {
        "require_finalisation": True
    }
    assert expected.is_dir()


def test_main_window_and_existing_map_wizard_construct(qtbot, tmp_path, configured_maps):
    app = QApplication.instance()
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setStyleSheet(STYLE)
    assert "QComboBox QAbstractItemView::item:selected" in STYLE
    assert "selection-color: #fffdf5" in STYLE
    assert "QPushButton, QToolButton { padding: 5px 9px; }" in STYLE
    assert "background: #fffdf7; color: #171714" in STYLE
    assert "QComboBox::down-arrow" in STYLE
    assert "border-top: 6px solid #39372f" in STYLE
    assert "QScrollBar::handle" in STYLE
    assert "Segoe UI" not in STYLE
    maps = configured_maps
    service = ApplicationService(
        FileGameRepository(RecentGameStore(tmp_path / "app.json")),
        maps,
        StandardRulesEngine(),
        VisibilityProjector(),
        MapRenderer(),
    )
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = ApplicationWindow(service, settings=settings)
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
    map_controls = window.map_workspace.outer_layout.itemAt(0).layout()
    assert (
        map_controls.indexOf(window.map_workspace.mode)
        < map_controls.indexOf(window.map_workspace.labels)
        < map_controls.indexOf(window.map_workspace.preview_orders)
    )
    assert window.map_workspace.fog_badge.parent() is window.map_workspace.canvas
    assert window.map_workspace.outcomes.parent() is window.map_workspace.canvas
    assert window.map_workspace.canvas.frameShape() is QFrame.Shape.NoFrame
    assert window.map_workspace.views.minimumWidth() == 240
    assert window.map_workspace.views.minimumContentsLength() == 26
    assert (
        window.map_workspace.views.sizeAdjustPolicy()
        is QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )
    window.map_workspace.mode.setCurrentIndex(
        window.map_workspace.mode.findData(DisplayMode.POSITION)
    )
    assert window.map_workspace.preview_orders.isCheckable()
    assert not window.map_workspace.preview_orders.isChecked()
    window.map_workspace.preview_orders.click()
    assert window.map_workspace.preview_orders.isChecked()
    assert window.map_workspace.preview_orders.text() == "Hide orders on map"
    window.map_workspace.labels.setCurrentIndex(1)
    render_request = window.map_workspace._request()
    assert render_request.display_mode is DisplayMode.ORDERS
    assert render_request.label_mode is LabelMode.ABBREVIATION
    window.map_workspace.preview_orders.click()
    assert not window.map_workspace.preview_orders.isChecked()
    assert window.map_workspace.preview_orders.text() == "Preview orders on map"
    window.show()
    QApplication.processEvents()
    control_palette = window.map_workspace.views.palette()
    assert control_palette.color(QPalette.ColorRole.Button).name() == "#fffaf0"
    assert control_palette.color(QPalette.ColorRole.ButtonText).name() == "#292820"
    assert window.statusBar().isHidden()
    assert not hasattr(window, "current_label")
    assert "A London - Wales" in window.orders_workspace.syntax_examples.text()
    assert "A London R Wales" in window.orders_workspace.syntax_examples.text()
    assert "A London B" in window.orders_workspace.syntax_examples.text()

    wizard = MapWizard(service, service.load_map_draft(maps.list()[0].map_id))
    qtbot.addWidget(wizard)
    wizard.resize(1400, 900)
    wizard.show()
    QApplication.processEvents()
    for index in range(wizard.tabs.count()):
        page = wizard.tabs.widget(index)
        assert page.palette().color(QPalette.ColorRole.WindowText).name() == "#292820"
    assert wizard.yaml_editor.palette().color(QPalette.ColorRole.Text).name() == "#171714"
    default_fit_canvas = MapCanvas()
    qtbot.addWidget(default_fit_canvas)
    default_fit_canvas.resize(320, 240)
    default_fit_canvas.set_svg(wizard.draft.svg)
    assert default_fit_canvas.transform().m11() < 1
    assert (
        wizard.anchor_canvas.viewportUpdateMode()
        is QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate
    )
    assert wizard.tabs.count() == 3
    assert tuple(wizard.tabs.tabText(index) for index in range(wizard.tabs.count())) == (
        "Definition",
        "Powers & start",
        "Placement",
    )
    assert not any(
        button.text().startswith(("Choose army", "Choose fleet"))
        for button in wizard.findChildren(QPushButton)
    )
    assert wizard.validation_label.text().startswith("Valid:")
    assert wizard.outer_layout.contentsMargins().left() == 4
    assert wizard.tabs.widget(2).layout().contentsMargins().left() == 2
    assert wizard.placement_layers_group.title() == "Preview layers"
    assert wizard.placement_labels_group.title() == "Territory labels"
    assert wizard.label_sizes_group.title() == "Label sizes"
    assert wizard.setup_page.map_colours_group.title() == "Map colours"
    assert wizard.tabs.widget(1).isAncestorOf(wizard.setup_page.map_colours_group)
    assert wizard.territory_group.title() == "Selected territory"
    assert {label.text() for label in wizard.territory_group.findChildren(QLabel)} >= {
        "Territory",
        "Canonical name",
        "Abbreviation",
        "Map display name",
    }
    territory_fields = (
        wizard.territory_selector,
        wizard.canonical_name_editor,
        wizard.abbreviation_editor,
        wizard.display_name_editor,
    )
    assert {field.minimumHeight() for field in territory_fields} == {34}
    assert {field.maximumHeight() for field in territory_fields} == {34}
    assert wizard.coast_label_group.title() == "Selected coast label"
    assert wizard.placement_labels.minimumWidth() == 150
    assert wizard.territory_font_size.singleStep() == 0.5
    assert wizard.coast_font_size.singleStep() == 0.5
    assert wizard.coast_rotation.minimumWidth() == 90
    assert wizard.yaml_editor.textCursor().selectedText() == "territories:"
    assert wizard.yaml_find.find_shortcut.key() in QKeySequence.keyBindings(
        QKeySequence.StandardKey.Find
    )
    wizard.tabs.setCurrentIndex(0)
    wizard.yaml_find.show_find()
    wizard.yaml_find.query.setText("split_coasts:")
    assert wizard.yaml_editor.textCursor().selectedText() == "split_coasts:"
    wizard.yaml_find.close_find()
    assert wizard.yaml_find.isHidden()
    assert wizard.save_button.text() == "Save configured map"
    for index in range(wizard.tabs.count()):
        wizard.tabs.setCurrentIndex(index)
        assert wizard.save_button.isEnabled()
    wizard.tabs.setCurrentIndex(0)
    wizard.yaml_editor.appendPlainText("\n# Retained when changing tabs")
    assert wizard.yaml_editor.document().isModified()
    wizard.tabs.setCurrentIndex(1)
    assert "# Retained when changing tabs" in wizard.draft.map_yaml
    assert not wizard.yaml_editor.document().isModified()
    power_id = wizard.setup_page.powers.item(0, 0).text()
    wizard.setup_page._set_power_colour(0, "#123456")
    assert wizard.setup_page.apply_changes(), wizard.setup_page.status.text()
    wizard.tabs.setCurrentIndex(2)
    assert yaml.safe_load(wizard.draft.map_yaml)["teams"][power_id]["colour"] == "#123456"
    assert wizard.setup_page.status.text() == "Powers and starting position applied"
    assert wizard.setup_page.canvas._renderer is not None
    assert wizard.setup_page.canvas._renderer.isValid()
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
    wizard.tabs.setCurrentIndex(0)
    QApplication.processEvents()
    yaml_width, map_width = wizard.topology_splitter.sizes()
    assert map_width >= yaml_width * 2
    assert wizard.topology_splitter.handleWidth() == 2
    wizard.tabs.setCurrentIndex(2)
    assert {label.attrib["font-size"] for label in node_layer.findall("{*}text")} == {"11"}
    assert {label.attrib["fill"] for label in node_layer.findall("{*}text")} == {"#111111"}
    assert all("stroke" not in label.attrib for label in node_layer.findall("{*}text"))
    assert {label.text for label in topology_coast_labels.findall("{*}g/{*}text")} >= {
        "North Coast",
        "South Coast",
    }
    assert {
        label.attrib["font-size"] for label in topology_coast_labels.findall("{*}g/{*}text")
    } == {"8"}
    assert {label.attrib["fill"] for label in topology_coast_labels.findall("{*}g/{*}text")} == {
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
    assert wizard.setup_page.canvas._renderer.elementExists("units")
    multiline_label = TextAnchorItem(
        Point(0, 0), "Derbyshire & Nottinghamshire", "#111111", lambda _point: None
    )
    assert multiline_label.rendered_text == "Derbyshire &\nNottinghamshire"
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
    assert not wizard.placement_zoom.percentage.focusPolicy() & Qt.FocusPolicy.TabFocus
    zoomed_in = wizard.anchor_canvas.transform().m11()
    wizard.placement_zoom.zoom_out.click()
    assert wizard.anchor_canvas.transform().m11() < zoomed_in
    wizard.anchor_canvas.set_standard_zoom()
    before_scale = wizard.anchor_canvas.transform().m11()
    assert wizard.placement_zoom.y() == 8
    assert (
        wizard.placement_zoom.x()
        == wizard.anchor_canvas.width() - wizard.placement_zoom.width() - 12
    )
    anchored_position = wizard.placement_zoom.pos()
    wheel_position = QPointF(50, 50)
    mouse_wheel = QWheelEvent(
        wheel_position,
        wheel_position,
        QPoint(0, 12),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
        Qt.MouseEventSource.MouseEventNotSynthesized,
    )
    wizard.anchor_canvas.wheelEvent(mouse_wheel)
    assert wizard.anchor_canvas.transform().m11() > before_scale
    assert wizard.placement_zoom.pos() == anchored_position
    assert wizard.anchor_canvas.verticalScrollBar().width() <= 8
    for controls in (
        wizard.topology_zoom,
        wizard.setup_page.zoom,
        wizard.placement_zoom,
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
    assert wizard.hold_underlines_group.title() == "Hold underlines"
    assert wizard.army_hold_group.title() == "Armies"
    assert wizard.fleet_hold_group.title() == "Fleets"
    assert all(len(item.childItems()) == 2 for item in army_items)
    army_offset = Point(4, 16)
    wizard.army_hold_x.setValue(army_offset.x)
    wizard.army_hold_y.setValue(army_offset.y)
    assert wizard.draft.presentation.army_hold_offset == army_offset
    assert all(item.hold_offset == army_offset for item in army_items)
    assert all(item.hold_line.pen().widthF() == 4 for item in army_items)
    assert yaml.safe_load(wizard.draft.map_yaml)["presentation"]["hold_underlines"]["army"] == [
        4.0,
        16.0,
    ]
    assert all(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable for item in army_items)
    assert all(
        not item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable for item in army_items
    )
    territory_names = {territory.name for territory in wizard.draft.territories}
    assert all(
        item.toolTip().startswith("Home territory: ")
        and any(name in item.toolTip() for name in territory_names)
        and item.toolTip().endswith("— army")
        for item in army_items
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
    assert all(
        item.toolTip().startswith("Home territory: ")
        and any(name in item.toolTip() for name in territory_names)
        and item.toolTip().endswith("— supply centre")
        for item in centre_items
    )
    selectable_labels = [
        item
        for item in wizard.anchor_canvas.scene().items()
        if isinstance(item, TextAnchorItem)
        and item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
    ]
    selectable_coast_labels = [item for item in selectable_labels if item.italic]
    selectable_territory_labels = [item for item in selectable_labels if not item.italic]
    assert len(selectable_coast_labels) == len(wizard.draft.presentation.coast_label_anchors)
    assert len(selectable_territory_labels) == len(wizard.draft.presentation.label_anchors)
    assert {label.font_size for label in selectable_coast_labels} == {8.0}
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
    placement_label = next(
        item
        for item in wizard.anchor_canvas.scene().items()
        if isinstance(item, TextAnchorItem)
        and item.rendered_text == "First display line\nSecond display line"
    )
    assert placement_label.rendered_text.splitlines() == [
        "First display line",
        "Second display line",
    ]
    composed_preview = ElementTree.fromstring(wizard._preview_svg_without())
    composed_label = next(
        label
        for label in composed_preview.findall(".//{*}g[@id='territory-labels']/{*}g")
        if "".join(line.text or "" for line in label.findall("{*}text"))
        == "First display lineSecond display line"
    )
    composed_lines = composed_label.findall("{*}text")
    assert [line.text for line in composed_lines] == [
        "First display line",
        "Second display line",
    ]
    assert len({line.attrib["y"] for line in composed_lines}) == 2
    assert all("dy" not in line.attrib for line in composed_lines)
    topology_preview = ElementTree.fromstring(
        wizard._topology_svg(service.preview_map_definition(wizard.draft))
    )
    assert any(
        "".join(line.text or "" for line in label.findall("{*}text"))
        == "First display lineSecond display line"
        for label in topology_preview.findall(".//{*}g[@id='territory-labels']/{*}g")
    )
    assert wizard.setup_page.reload_preview()
    assert wizard.setup_page.canvas._renderer.elementExists("territory-labels")
    wizard.territory_font_size.setValue(12.5)
    wizard.coast_font_size.setValue(8.5)
    assert wizard.draft.presentation.territory_label_font_size == 12.5
    assert wizard.draft.presentation.coast_label_font_size == 8.5
    resized_labels = [
        item for item in wizard.anchor_canvas.scene().items() if isinstance(item, TextAnchorItem)
    ]
    assert {item.font_size for item in resized_labels if not item.italic} == {12.5}
    assert {item.font_size for item in resized_labels if item.italic} == {8.5}
    wizard.setup_page._set_map_colour("label_colour", "#201810")
    wizard.setup_page._set_map_colour("inaccessible_region_colour", "#303030")
    wizard.setup_page._set_map_colour("sea_colour", "#406080")
    wizard.setup_page._set_map_colour("unclaimed_region_colour", "#d8c8a8")
    assert wizard.setup_page.label_colour_button.text() == "Text #201810"
    assert wizard.setup_page.inaccessible_colour_button.text() == "Inaccessible #303030"
    assert wizard.setup_page.sea_colour_button.text() == "Sea #406080"
    assert wizard.setup_page.unclaimed_colour_button.text() == "Unclaimed #D8C8A8"
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
    fleet_items = [
        item
        for item in wizard.anchor_canvas.scene().items()
        if isinstance(item, UnitAnchorItem) and "— fleet" in item.toolTip()
    ]
    assert len(fleet_items) == len(wizard.draft.presentation.fleet_anchors)
    fleet_offset = Point(-3, 18)
    wizard.fleet_hold_x.setValue(fleet_offset.x)
    wizard.fleet_hold_y.setValue(fleet_offset.y)
    assert wizard.draft.presentation.fleet_hold_offset == fleet_offset
    assert all(item.hold_offset == fleet_offset for item in fleet_items)
    assert all(
        item.toolTip().startswith("Home territory: ")
        and any(name in item.toolTip() for name in territory_names)
        for item in fleet_items
    )
    assert sum(", " in item.toolTip() for item in fleet_items) == sum(
        location.coast_id is not None for location in wizard.draft.presentation.fleet_anchors
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
    wizard._select_territory_label(renamed_territory.id)
    wizard.canonical_name_editor.setText("Persisted place name")
    wizard.abbreviation_editor.setText("Ppn")
    wizard._apply_territory_details()
    assert (
        next(
            territory.name
            for territory in wizard.draft.territories
            if territory.id == renamed_territory.id
        )
        == "Persisted place name"
    )
    assert (
        next(
            territory.abbreviation
            for territory in wizard.draft.territories
            if territory.id == renamed_territory.id
        )
        == "Ppn"
    )
    saved = []
    wizard.saved.connect(saved.append)
    wizard.tabs.setCurrentIndex(2)
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
    assert maps.load(saved[0].id).presentation.army_hold_offset == army_offset
    assert maps.load(saved[0].id).presentation.fleet_hold_offset == fleet_offset
    assert maps.load(saved[0].id).presentation.unclaimed_region_colour == "#d8c8a8"
    reopened_maps = FileMapLibrary(tmp_path / "maps")
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


def test_current_game_opens_full_map_editor(qtbot, tmp_path, configured_maps, monkeypatch):
    maps = configured_maps
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
    settings = QSettings(str(tmp_path / "image-settings.ini"), QSettings.Format.IniFormat)
    window = ApplicationWindow(service, settings=settings)
    qtbot.addWidget(window)
    window.map_workspace.labels.setCurrentIndex(1)
    window.set_session(session, open_map=True)
    assert LabelMode(window.map_workspace.labels.currentData()) is LabelMode.FULL_NAME
    assert window.phase_selector.minimumWidth() == 170
    assert window.phase_selector.minimumContentsLength() == len("Year End 1901")
    assert (
        window.phase_selector.sizeAdjustPolicy()
        is QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )
    assert not window.previous.isEnabled()
    assert not window.next.isEnabled()
    assert window.previous.property("seasonNavigation")
    assert window.next.property("seasonNavigation")
    assert not window.game_map_edit_button.isHidden()
    assert window.tabs.currentIndex() == 0
    assert window.stack.currentWidget() is window.map_workspace
    assert window.phase_selector.currentData() == session.phase.phase_id
    window.tabs.setCurrentIndex(1)
    assert window.stack.currentWidget() is window.orders_workspace
    assert window.orders_workspace.unfinalised.isHidden()
    assert window.orders_workspace.final_count.isHidden()
    assert all(panel.final is None for panel in window.orders_workspace.panels)
    window.show()
    QApplication.processEvents()
    season_bar_top = window.season_bar.geometry().top()
    preview_unit = session.phase.state.units[0]
    preview_territory = next(
        territory
        for territory in configured.territories
        if territory.id == preview_unit.location.territory_id
    )
    preview_panel = next(
        panel for panel in window.orders_workspace.panels if panel.power.id == preview_unit.power_id
    )
    assert preview_panel.editor is not None
    assert preview_panel.objectName() == "powerPanel"
    assert "QFrame#powerPanel" in preview_panel.styleSheet()
    assert "QFrame {" not in preview_panel.styleSheet()
    canonical_orders = preview_panel.stack.widget(0)
    assert {
        preview_panel.stack.minimumHeight(),
        preview_panel.stack.maximumHeight(),
        canonical_orders.minimumHeight(),
        canonical_orders.maximumHeight(),
        preview_panel.editor.minimumHeight(),
        preview_panel.editor.maximumHeight(),
    } == {96}
    canonical_height = preview_panel.sizeHint().height()
    qtbot.mouseClick(canonical_orders, Qt.MouseButton.LeftButton)
    assert preview_panel.editor.hasFocus()
    assert preview_panel.sizeHint().height() == canonical_height
    preview_panel.editor.setPlainText("A Not Yet Complete -")
    qtbot.wait(550)
    assert window.order_feedback.text() == ""
    assert preview_panel in window.orders_workspace.panels
    assert preview_panel.stack.currentIndex() == 1
    assert preview_panel.sizeHint().height() == canonical_height
    other_panel = next(
        panel for panel in window.orders_workspace.panels if panel.power.id != preview_unit.power_id
    )
    other_power_id = other_panel.power.id
    qtbot.mouseClick(other_panel.canonical, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: preview_panel not in window.orders_workspace.panels)
    assert window.order_feedback.text() == "Orders saved and validated"
    assert window.season_bar.geometry().top() == season_bar_top
    preview_panel = next(
        panel for panel in window.orders_workspace.panels if panel.power.id == preview_unit.power_id
    )
    other_panel = next(
        panel for panel in window.orders_workspace.panels if panel.power.id == other_power_id
    )
    assert other_panel.stack.currentIndex() == 1
    assert other_panel.editor is not None and other_panel.editor.hasFocus()
    tab_target_power = next(
        panel.power.id
        for panel in window.orders_workspace.panels
        if panel.editor is not None
        and panel.power.id not in {other_power_id, preview_unit.power_id}
    )
    qtbot.keyClick(other_panel.editor, Qt.Key.Key_Tab)
    qtbot.waitUntil(
        lambda: any(
            panel.power.id == tab_target_power
            and panel.editor is not None
            and panel.editor.hasFocus()
            for panel in window.orders_workspace.panels
        )
    )
    unparseable_summary = preview_panel.canonical.text()
    assert "#a32620" in unparseable_summary
    assert "A&nbsp;Not&nbsp;Yet&nbsp;Complete&nbsp;- (??)" in unparseable_summary
    qtbot.mouseClick(preview_panel.canonical, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: other_panel not in window.orders_workspace.panels)
    preview_panel = next(
        panel for panel in window.orders_workspace.panels if panel.power.id == preview_unit.power_id
    )
    assert preview_panel.stack.currentIndex() == 1
    assert preview_panel.editor is not None
    assert preview_panel.editor.hasFocus()
    assert preview_panel.editor.toPlainText() == "A Not Yet Complete -"
    preview_panel.editor.setPlainText(
        f"{preview_unit.unit_type.value[0].upper()} {preview_territory.name} H"
    )
    preview_panel.editor.moveCursor(QTextCursor.MoveOperation.End)
    qtbot.keyClick(preview_panel.editor, Qt.Key.Key_Return)
    qtbot.wait(550)
    assert preview_panel in window.orders_workspace.panels
    assert preview_panel.stack.currentIndex() == 1
    assert "\n" in preview_panel.editor.toPlainText()
    original_text = preview_panel.editor.toPlainText()
    QApplication.sendEvent(preview_panel.editor, QFocusEvent(QEvent.Type.FocusOut))
    qtbot.waitUntil(lambda: preview_panel not in window.orders_workspace.panels)
    preview_panel = next(
        panel for panel in window.orders_workspace.panels if panel.power.id == preview_unit.power_id
    )
    assert preview_panel.stack.currentIndex() == 0
    assert preview_panel.editor is not None
    canonical_orders = preview_panel.stack.widget(0)
    assert canonical_orders.text() == f"A&nbsp;{preview_territory.abbreviation}&nbsp;H"
    qtbot.mouseClick(canonical_orders, Qt.MouseButton.LeftButton)
    assert preview_panel.stack.currentIndex() == 1
    assert preview_panel.editor.toPlainText() == original_text
    preview_panel.editor.setPlainText(
        f"{preview_unit.unit_type.value[0].upper()} {preview_territory.name} H"
    )
    assert window.orders_workspace.pending_order_texts() == (
        (preview_unit.power_id, preview_panel.editor.toPlainText()),
    )
    window.orders_workspace.preview.click()
    assert window.tabs.currentIndex() == 0
    assert window.stack.currentWidget() is window.map_workspace
    assert DisplayMode(window.map_workspace.mode.currentData()) is DisplayMode.ORDERS
    assert window.session.phase.phase_id == session.phase.phase_id
    assert window.session.phase.state == session.phase.state
    window.map_workspace.refresh_timer.stop()
    window.map_workspace.refresh()
    preview_svg = ElementTree.fromstring(window.map_workspace.scene.svg)
    preview_orders = next(
        group for group in preview_svg.findall(".//{*}g") if group.attrib.get("id") == "orders"
    )
    assert preview_orders.find(".//{*}line[@class='hold-marker']") is not None
    advanced = service.resolve_and_advance()
    window.set_session(advanced.session, open_map=True)
    spring_index = window.phase_selector.findData(session.phase.phase_id)
    window.phase_selector.setCurrentIndex(spring_index)
    qtbot.waitUntil(lambda: window.session.phase.phase_id == session.phase.phase_id)
    assert window.map_workspace.preview_orders.isChecked()
    window.map_workspace.preview_orders.click()
    assert not window.map_workspace.preview_orders.isChecked()
    window.map_workspace.refresh_timer.stop()
    window.map_workspace.refresh()
    position_orders = ElementTree.fromstring(window.map_workspace.scene.svg)
    position_order_layer = next(
        group for group in position_orders.findall(".//{*}g") if group.attrib.get("id") == "orders"
    )
    assert not list(position_order_layer)
    window.tabs.setCurrentIndex(0)
    assert window.stack.currentWidget() is window.map_workspace
    window.map_workspace.refresh()
    window.map_workspace.views.setCurrentIndex(window.map_workspace.views.findData(None))
    window.map_workspace._view_changed()
    full_map_output = window.map_workspace._export_current_view()
    expected_full_map_size = aspect_fitted_size(
        window.map_workspace.canvas.visible_bounds(),
        PixelSize(
            window.map_workspace.canvas.viewport().width(),
            window.map_workspace.canvas.viewport().height(),
        ),
    )
    expected_full_map_size = PixelSize(
        expected_full_map_size.width * 2,
        expected_full_map_size.height * 2,
    )
    expected_full_map_size = aspect_fitted_size(
        window.map_workspace.scene.map_bounds,
        expected_full_map_size,
    )
    assert full_map_output.size == expected_full_map_size
    assert full_map_output.size.width / full_map_output.size.height == pytest.approx(
        window.map_workspace.scene.map_bounds.width / window.map_workspace.scene.map_bounds.height,
        abs=1 / full_map_output.size.height,
    )
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
    saved_image = tmp_path / "saved-map.png"
    dialog_initial_paths = []

    def choose_saved_image(_parent, _title, initial_path, _filter):
        dialog_initial_paths.append(initial_path)
        return str(saved_image), "PNG images (*.png)"

    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose_saved_image)
    window.map_workspace._save_image()
    assert saved_image.read_bytes().startswith(b"\x89PNG")
    assert window.map_workspace.save_image_button.text() == "Saved"
    assert Path(dialog_initial_paths[0]).parent == Path(".")

    second_image = tmp_path / "another-folder" / "second-map.png"
    second_image.parent.mkdir()

    def choose_second_image(_parent, _title, initial_path, _filter):
        dialog_initial_paths.append(initial_path)
        return str(second_image), "PNG images (*.png)"

    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose_second_image)
    window.map_workspace._save_image()
    assert Path(dialog_initial_paths[1]).parent == tmp_path
    assert settings.value("imageSharing/lastDirectory") == str(second_image.parent.resolve())

    window.game_map_edit_button.click()
    editor = window.stack.currentWidget()
    assert isinstance(editor, MapWizard)
    assert editor.game_map
    assert [editor.tabs.tabText(index) for index in range(editor.tabs.count())] == [
        "Definition",
        "Powers & start",
        "Placement",
    ]
    assert editor.save_button.text() == "Save game map"
    assert editor.yaml_editor.toPlainText()

    territory_id, old_point = next(iter(editor.draft.presentation.label_anchors.items()))
    editor.army_hold_x.setValue(6)
    editor.army_hold_y.setValue(17)
    moved_point = Point(old_point.x + 3, old_point.y + 5)
    editor._anchor_moved(territory_id, "label", None, moved_point)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: QMessageBox.StandardButton.Save,
    )
    editor.save_button.click()
    assert window.stack.currentWidget() is window.map_workspace
    assert (
        window.session.game.map_definition.presentation.label_anchors[territory_id] == moved_point
    )
    assert window.session.game.map_definition.presentation.army_hold_offset == Point(6, 17)

    window._show_game_choices()
    assert window.stack.currentWidget() is window.welcome
    delete_buttons = [
        button for button in window.welcome.findChildren(QPushButton) if button.text() == "Delete…"
    ]
    assert len(delete_buttons) == 1
    delete_buttons[0].click()
    assert not window.delete_confirmation.isHidden()
    assert "Placement UI game" in window.delete_confirmation_text.text()
    assert str(session.game.location.path) in window.delete_confirmation_text.text()
    window._cancel_game_deletion()
    assert window.delete_confirmation.isHidden()
    assert session.game.location.path.exists()
    window._request_game_deletion(session.game.location, session.game.name)
    window.confirm_delete_game.click()
    assert not session.game.location.path.exists()
    assert window.session.game is None
    assert window.stack.currentWidget() is window.welcome
