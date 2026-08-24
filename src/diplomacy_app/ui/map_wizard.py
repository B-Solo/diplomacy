"""Tabbed custom SVG map configuration editor."""

from __future__ import annotations

import math
import re
from dataclasses import replace
from typing import Any
from xml.etree import ElementTree

import yaml
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCursor, QTextDocument, QTextFormat
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from shapely.geometry import Point as GeometryPoint

from diplomacy_app.domain.models import (
    CoastId,
    Location,
    MapDraft,
    Point,
    SvgElementRole,
    TerritoryKind,
    UnitType,
)
from diplomacy_app.map_library.defaults import DEFAULT_ARMY_SVG, DEFAULT_FLEET_SVG
from diplomacy_app.map_library.svg_importer import territory_geometries
from diplomacy_app.presentation import (
    coast_label_text,
    darken_colour,
    embedded_unit_svg,
)
from diplomacy_app.ui.map_canvas import (
    MapCanvas,
    MapZoomControls,
    SupplyCentreAnchorItem,
    TextAnchorItem,
    UnitAnchorItem,
)


class YamlFindBar(QWidget):
    """Inline, wrapping search controls for a YAML text editor."""

    def __init__(self, editor: QPlainTextEdit, shortcut_parent: QWidget) -> None:
        super().__init__()
        self.editor = editor
        self._origin = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(4)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Find in YAML")
        self.query.setClearButtonEnabled(True)
        layout.addWidget(self.query, 1)
        previous = QToolButton()
        previous.setText("↑")
        previous.setToolTip("Previous match (Shift+Enter)")
        previous.clicked.connect(lambda: self.find_match(backward=True))
        layout.addWidget(previous)
        following = QToolButton()
        following.setText("↓")
        following.setToolTip("Next match (Enter)")
        following.clicked.connect(self.find_match)
        layout.addWidget(following)
        close = QToolButton()
        close.setText("×")
        close.setToolTip("Close find (Escape)")
        close.clicked.connect(self.close_find)
        layout.addWidget(close)

        self.find_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Find), shortcut_parent)
        self.find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.find_shortcut.activated.connect(self.show_find)
        self.previous_shortcut = QShortcut(QKeySequence("Shift+Return"), self.query)
        self.previous_shortcut.activated.connect(lambda: self.find_match(backward=True))
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.escape_shortcut.activated.connect(self.close_find)
        self.query.returnPressed.connect(self.find_match)
        self.query.textChanged.connect(lambda _text: self.find_match(from_origin=True))
        self.hide()

    def show_find(self) -> None:
        cursor = self.editor.textCursor()
        selected = cursor.selectedText()
        self._origin = cursor.selectionStart()
        if selected and "\u2029" not in selected:
            self.query.setText(selected)
        self.show()
        self.query.setFocus()
        self.query.selectAll()

    def close_find(self) -> None:
        self.hide()
        self.editor.setFocus()

    def find_match(self, backward: bool = False, from_origin: bool = False) -> None:
        query = self.query.text()
        if not query:
            self.query.setStyleSheet("")
            return
        if from_origin:
            cursor = QTextCursor(self.editor.document())
            cursor.setPosition(self._origin)
            self.editor.setTextCursor(cursor)
        flag = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        found = self.editor.find(query, flag)
        if not found:
            cursor = QTextCursor(self.editor.document())
            cursor.movePosition(
                QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start
            )
            self.editor.setTextCursor(cursor)
            found = self.editor.find(query, flag)
        self.query.setStyleSheet(
            "" if found else "QLineEdit { background: #f4d8d3; color: #551f1a; }"
        )


class DisplayNameEdit(QPlainTextEdit):
    """Multiline display-name editor whose unmodified Enter key applies."""

    apply_requested = Signal()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.apply_requested.emit()
            return
        super().keyPressEvent(event)


class MapWizard(QWidget):
    cancelled = Signal()
    saved = Signal(object)

    def __init__(
        self, service, draft: MapDraft, parent=None, *, game_placement_only: bool = False
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.draft = draft
        self.game_placement_only = game_placement_only
        self.saved_definition = None
        self._element_geometries = (
            {} if game_placement_only else territory_geometries(draft.svg, draft.element_roles)
        )
        self._row_by_element: dict[str, int] = {}
        self._populating_roles = False
        self._topology_nodes: dict[str, Point] = {}
        self._topology_node_territories: dict[str, str] = {}
        self._topology_names: dict[str, str] = {}
        self._topology_hovered_territory: str | None = None
        self._selected_territory_label = None
        self._selected_coast_label: Location | None = None
        self._coast_label_items: dict[Location, TextAnchorItem] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(3)
        self.outer_layout = layout
        if game_placement_only:
            scope = QLabel(
                "Adjust this game's private visual placement. Territory names, rules, "
                "topology, powers and setup remain unchanged."
            )
            scope.setWordWrap(True)
            scope.setProperty("muted", True)
            layout.addWidget(scope)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        if game_placement_only:
            self._build_anchor_tab()
        else:
            self._build_classification_tab()
            self._build_yaml_tab()
            self._build_setup_tab()
            self._build_anchor_tab()
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setVisible(False)
        layout.addWidget(self.message)
        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.cancelled)
        buttons.addWidget(cancel)
        buttons.addStretch()
        self.save_button = QPushButton(
            "Save game map placement" if game_placement_only else "Save configured map"
        )
        self.save_button.setProperty("primary", True)
        self.save_button.clicked.connect(self._save)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self._reload_anchor_scene()
        if not game_placement_only:
            self.yaml_editor.setPlainText(draft.map_yaml)
            self._populate_roles()
            self.tabs.currentChanged.connect(self._tab_changed)
            self._validate()
            self._reload_classification_preview()
            self._reload_setup_preview()
            self._focus_topology_section()

    def _build_classification_tab(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        self.preview = MapCanvas()
        self.preview.set_svg(self.draft.svg, fit=True)
        self.hovered_territory = QLabel("Hover over a territory or row to identify it.")
        self.hovered_territory.setProperty("muted", True)
        map_side = QWidget()
        map_layout = QVBoxLayout(map_side)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.addWidget(self.preview, 1)
        self.regions_zoom = MapZoomControls(self.preview)
        map_layout.addWidget(self.hovered_territory)
        self.roles = QTableWidget(0, 3)
        self.roles.setHorizontalHeaderLabels(["Canonical territory", "SVG element", "Role"])
        self.roles.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.roles.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.roles.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.roles.setMouseTracking(True)
        self.roles.cellEntered.connect(lambda row, _column: self._highlight_row(row))
        self.roles.currentCellChanged.connect(
            lambda row, _column, _old_row, _old_column: self._highlight_row(row)
        )
        self.roles.itemChanged.connect(self._territory_name_changed)
        self.preview.scene_hovered.connect(self._map_hovered)
        splitter = QSplitter()
        splitter.setHandleWidth(2)
        splitter.addWidget(map_side)
        splitter.addWidget(self.roles)
        splitter.setSizes([820, 280])
        layout.addWidget(splitter)
        self.tabs.addTab(page, "SVG regions")

    def _build_yaml_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)
        legend = QLabel(
            '<span style="color:#f4511e; font-weight:700">━━ Army</span>&nbsp;&nbsp; '
            '<span style="color:#00b8d4; font-weight:700">━━ Fleet</span>&nbsp;&nbsp; '
            '<span style="color:#d500f9; font-weight:700">━━ Both</span>&nbsp;&nbsp; '
            "→ one-way &nbsp;&nbsp; ○ node"
        )
        layout.addWidget(legend)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        self.yaml_editor = QPlainTextEdit()
        self.yaml_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        yaml_side = QWidget()
        yaml_layout = QVBoxLayout(yaml_side)
        yaml_layout.setContentsMargins(0, 0, 0, 0)
        self.yaml_find = YamlFindBar(self.yaml_editor, page)
        yaml_layout.addWidget(self.yaml_find)
        yaml_layout.addWidget(self.yaml_editor, 1)
        self.topology_canvas = MapCanvas()
        self.topology_canvas.scene_hovered.connect(self._topology_hovered)
        topology_side = QWidget()
        topology_layout = QVBoxLayout(topology_side)
        topology_layout.setContentsMargins(0, 0, 0, 0)
        topology_layout.addWidget(self.topology_canvas, 1)
        self.topology_zoom = MapZoomControls(self.topology_canvas)
        splitter.addWidget(yaml_side)
        splitter.addWidget(topology_side)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([300, 860])
        self.topology_splitter = splitter
        layout.addWidget(splitter, 1)
        controls = QHBoxLayout()
        validate = QPushButton("Validate and compile")
        validate.clicked.connect(self._validate)
        controls.addWidget(validate)
        self.validation_label = QLabel("Not yet validated")
        self.validation_label.setWordWrap(True)
        controls.addWidget(self.validation_label, 1)
        layout.addLayout(controls)
        self.tabs.addTab(page, "Topology")

    def _build_setup_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        editor_side = QWidget()
        editor_layout = QVBoxLayout(editor_side)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        self.setup_editor = QPlainTextEdit()
        self.setup_editor.setObjectName("setupEditor")
        self.setup_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setup_find = YamlFindBar(self.setup_editor, page)
        editor_layout.addWidget(self.setup_find)
        editor_layout.addWidget(self.setup_editor, 1)

        self.map_colours_group = QGroupBox("Map colours")
        colours_layout = QHBoxLayout(self.map_colours_group)
        colours_layout.setContentsMargins(10, 8, 10, 8)
        colours_layout.setSpacing(6)
        self.label_colour_button = QPushButton()
        self.inaccessible_colour_button = QPushButton()
        self.sea_colour_button = QPushButton()
        self.unclaimed_colour_button = QPushButton()
        for field, button in (
            ("label_colour", self.label_colour_button),
            ("inaccessible_region_colour", self.inaccessible_colour_button),
            ("sea_colour", self.sea_colour_button),
            ("unclaimed_region_colour", self.unclaimed_colour_button),
        ):
            button.clicked.connect(
                lambda _checked=False, field=field: self._choose_map_colour(field)
            )
            colours_layout.addWidget(button)
        self._refresh_colour_buttons()
        editor_layout.addWidget(self.map_colours_group)

        controls = QHBoxLayout()
        apply_setup = QPushButton("Regenerate map preview")
        apply_setup.clicked.connect(self._apply_setup_changes)
        controls.addWidget(apply_setup)
        self.setup_validation_label = QLabel()
        self.setup_validation_label.setWordWrap(True)
        controls.addWidget(self.setup_validation_label, 1)
        editor_layout.addLayout(controls)
        self.setup_canvas = MapCanvas()
        preview_side = QWidget()
        preview_layout = QVBoxLayout(preview_side)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(self.setup_canvas, 1)
        self.setup_zoom = MapZoomControls(self.setup_canvas)
        splitter.addWidget(editor_side)
        splitter.addWidget(preview_side)
        splitter.setSizes([430, 730])
        layout.addWidget(splitter, 1)
        self.setup_splitter = splitter
        self.tabs.addTab(page, "Powers and setup")

    def _build_anchor_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)
        preview_row = QHBoxLayout()
        preview_row.setSpacing(10)

        self.placement_layers_group = QGroupBox("Preview layers")
        layers_layout = QHBoxLayout(self.placement_layers_group)
        layers_layout.setContentsMargins(10, 8, 10, 8)
        layers_layout.setSpacing(12)
        self.armies_preview = QCheckBox("Armies")
        self.fleets_preview = QCheckBox("Fleets")
        self.supply_preview = QCheckBox("Supply centres")
        self.coast_labels_preview = QCheckBox("Coast labels")
        self.armies_preview.setChecked(True)
        self.armies_preview.toggled.connect(self._preview_changed)
        self.fleets_preview.toggled.connect(self._preview_changed)
        self.supply_preview.setChecked(True)
        self.supply_preview.toggled.connect(self._preview_changed)
        self.coast_labels_preview.setChecked(True)
        self.coast_labels_preview.toggled.connect(self._preview_changed)
        layers_layout.addWidget(self.armies_preview)
        layers_layout.addWidget(self.fleets_preview)
        layers_layout.addWidget(self.supply_preview)
        layers_layout.addWidget(self.coast_labels_preview)
        preview_row.addWidget(self.placement_layers_group, 2)

        self.placement_labels_group = QGroupBox("Territory labels")
        labels_layout = QHBoxLayout(self.placement_labels_group)
        labels_layout.setContentsMargins(10, 8, 10, 8)
        self.placement_labels = QComboBox()
        self.placement_labels.setMinimumWidth(150)
        self.placement_labels.addItem("None", None)
        self.placement_labels.addItem("Display names", "full")
        self.placement_labels.addItem("Abbreviations", "abbreviation")
        self.placement_labels.setCurrentIndex(1)
        self.placement_labels.currentIndexChanged.connect(self._reload_anchor_scene)
        labels_layout.addWidget(self.placement_labels)
        preview_row.addWidget(self.placement_labels_group)

        self.label_sizes_group = QGroupBox("Label sizes")
        sizes_layout = QHBoxLayout(self.label_sizes_group)
        sizes_layout.setContentsMargins(10, 8, 10, 8)
        sizes_layout.setSpacing(6)
        sizes_layout.addWidget(QLabel("Territory"))
        self.territory_font_size = QDoubleSpinBox()
        self.territory_font_size.setRange(5, 24)
        self.territory_font_size.setDecimals(1)
        self.territory_font_size.setSingleStep(0.5)
        self.territory_font_size.setSuffix(" pt")
        self.territory_font_size.setValue(self.draft.presentation.territory_label_font_size)
        sizes_layout.addWidget(self.territory_font_size)
        sizes_layout.addWidget(QLabel("Coasts"))
        self.coast_font_size = QDoubleSpinBox()
        self.coast_font_size.setRange(5, 24)
        self.coast_font_size.setDecimals(1)
        self.coast_font_size.setSingleStep(0.5)
        self.coast_font_size.setSuffix(" pt")
        self.coast_font_size.setValue(self.draft.presentation.coast_label_font_size)
        sizes_layout.addWidget(self.coast_font_size)
        self.territory_font_size.valueChanged.connect(self._label_font_sizes_changed)
        self.coast_font_size.valueChanged.connect(self._label_font_sizes_changed)
        preview_row.addWidget(self.label_sizes_group)
        preview_row.addStretch()
        layout.addLayout(preview_row)

        editing_row = QHBoxLayout()
        editing_row.setSpacing(10)

        if not self.game_placement_only:
            self.display_name_group = QGroupBox("Selected territory display name")
            display_layout = QHBoxLayout(self.display_name_group)
            display_layout.setContentsMargins(10, 8, 10, 8)
            display_layout.setSpacing(6)
            self.display_name_editor = DisplayNameEdit()
            self.display_name_editor.setPlaceholderText("Select a display-name label on the map")
            self.display_name_editor.setToolTip(
                "Press Enter to apply; press Shift+Enter to insert a line break."
            )
            self.display_name_editor.setFixedHeight(48)
            self.display_name_editor.setMinimumWidth(190)
            self.display_name_editor.apply_requested.connect(self._apply_display_name)
            display_layout.addWidget(self.display_name_editor)
            apply_display_name = QPushButton("Apply")
            apply_display_name.clicked.connect(self._apply_display_name)
            display_layout.addWidget(apply_display_name)
            self.display_name_group.setEnabled(False)
            editing_row.addWidget(self.display_name_group, 1)

        self.coast_label_group = QGroupBox("Selected coast label")
        coast_layout = QHBoxLayout(self.coast_label_group)
        coast_layout.setContentsMargins(10, 8, 10, 8)
        coast_layout.setSpacing(8)
        coast_layout.addWidget(QLabel("Rotation"))
        self.coast_rotation = QSpinBox()
        self.coast_rotation.setRange(-180, 180)
        self.coast_rotation.setSingleStep(5)
        self.coast_rotation.setSuffix("°")
        self.coast_rotation.setMinimumWidth(90)
        self.coast_rotation.setEnabled(False)
        self.coast_rotation.valueChanged.connect(self._coast_rotation_changed)
        coast_layout.addWidget(self.coast_rotation)
        editing_row.addWidget(self.coast_label_group)
        editing_row.addStretch()
        layout.addLayout(editing_row)
        self.anchor_canvas = MapCanvas()
        self.anchor_canvas.scene_pressed.connect(self._clear_label_selection)
        layout.addWidget(self.anchor_canvas, 1)
        self.placement_zoom = MapZoomControls(self.anchor_canvas)
        self.tabs.addTab(page, "Placement")

    def _populate_roles(self) -> None:
        self._populating_roles = True
        self.roles.setRowCount(0)
        self._row_by_element.clear()
        territory_names = {
            territory.svg_element_id: territory.name for territory in self.draft.territories
        }
        for element_id, role in sorted(self.draft.element_roles.items()):
            row = self.roles.rowCount()
            self.roles.insertRow(row)
            self._row_by_element[element_id] = row
            display_name = territory_names.get(element_id) or self._element_name(element_id, role)
            name_item = QTableWidgetItem(display_name)
            if role is not SvgElementRole.TERRITORY:
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.roles.setItem(row, 0, name_item)
            element_item = QTableWidgetItem(element_id)
            element_item.setFlags(element_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.roles.setItem(row, 1, element_item)
            selector = QComboBox()
            for value in SvgElementRole:
                selector.addItem(value.value.replace("_", " ").title(), value)
            selector.setCurrentIndex(selector.findData(role))
            selector.currentIndexChanged.connect(
                lambda _index, element_id=element_id, selector=selector: self._role_changed(
                    element_id, selector.currentData()
                )
            )
            self.roles.setCellWidget(row, 2, selector)
        self._populating_roles = False

    def _territory_name_changed(self, item: QTableWidgetItem) -> None:
        if self._populating_roles or item.column() != 0:
            return
        element_item = self.roles.item(item.row(), 1)
        if element_item is None:
            return
        territory = next(
            (
                territory
                for territory in self.draft.territories
                if territory.svg_element_id == element_item.text()
            ),
            None,
        )
        if territory is None or item.text().strip() == territory.name:
            return
        try:
            self._commit_editor()
            self.draft = self.service.update_map_territory_name(
                self.draft, territory.id, item.text()
            )
            self.yaml_editor.setPlainText(self.draft.map_yaml)
            item.setText(
                next(value.name for value in self.draft.territories if value.id == territory.id)
            )
            self._reload_classification_preview()
        except Exception as exc:
            self._populating_roles = True
            item.setText(territory.name)
            self._populating_roles = False
            self._show_error(f"Could not rename territory: {exc}")

    @staticmethod
    def _element_name(element_id: str, role: SvgElementRole) -> str:
        prefix = f"{role.value}-"
        name = element_id.removeprefix(prefix).replace("-", " ").strip()
        return name.title() if name else element_id

    def _highlight_row(self, row: int) -> None:
        element_item = self.roles.item(row, 1) if row >= 0 else None
        if element_item is None:
            return
        element_id = element_item.text()
        self.preview.highlight_element(element_id)
        territory = next(
            (item for item in self.draft.territories if item.svg_element_id == element_id), None
        )
        if territory:
            text = f"{territory.name} ({territory.abbreviation}) — {element_id}"
        else:
            role = self.draft.element_roles[element_id]
            text = f"{self._element_name(element_id, role)} — {role.value.title()} — {element_id}"
        self.hovered_territory.setText(text)

    def _map_hovered(self, x: float, y: float) -> None:
        point = GeometryPoint(x, y)
        priority = {
            SvgElementRole.TERRITORY: 0,
            SvgElementRole.IMPASSABLE: 1,
            SvgElementRole.DECORATION: 2,
        }
        candidates = [
            (priority[role], geometry.area, element_id)
            for element_id, role in self.draft.element_roles.items()
            if (geometry := self._element_geometries.get(element_id)) is not None
            if geometry.covers(point)
        ]
        if candidates:
            element_id = min(candidates)[2]
            row = self._row_by_element.get(element_id)
            if row is not None:
                self.roles.selectRow(row)
                territory_item = self.roles.item(row, 0)
                if territory_item is not None:
                    self.roles.scrollToItem(territory_item)
            self._highlight_row(row if row is not None else -1)
            return
        self.hovered_territory.setText("No classified region under the pointer.")
        self.preview.highlight_element(None)

    def _role_changed(self, element_id: str, role: SvgElementRole) -> None:
        try:
            self._commit_editor()
            self.draft = self.service.update_map_element_role(self.draft, element_id, role)
            self.yaml_editor.setPlainText(self.draft.map_yaml)
            self._element_geometries = territory_geometries(
                self.draft.svg, self.draft.element_roles
            )
            self._populate_roles()
            self._reload_classification_preview()
            self._reload_anchor_scene()
        except Exception as exc:
            self._show_error(f"Could not change region role: {exc}")

    def _commit_editor(self) -> None:
        self.draft = replace(self.draft, map_yaml=self.yaml_editor.toPlainText())

    def _preview_svg_without(self, *layer_ids: str) -> bytes:
        root = ElementTree.fromstring(self.service.preview_map_setup(self.draft).svg)
        for layer_id in layer_ids:
            layer = root.find(f".//{{*}}g[@id='{layer_id}']")
            if layer is not None:
                for child in list(layer):
                    layer.remove(child)
        return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)

    def _reload_classification_preview(self) -> None:
        try:
            self.preview.set_svg(self._preview_svg_without(), fit=True)
        except Exception:
            self.preview.set_svg(self.draft.svg, fit=True)

    def _validate(self) -> bool:
        self._commit_editor()
        validation = self.service.validate_map_draft(self.draft)
        if not validation.is_valid:
            text = "\n".join(
                f"• {item.issue.message} ({item.location.field})" for item in validation.issues
            )
            self.validation_label.setText(text)
            self.validation_label.setStyleSheet("color: #8a302b")
            self.topology_canvas.set_svg(self.draft.svg, fit=True)
            return False
        try:
            self.draft = self.service.refresh_map_draft(self.draft)
            definition = self.service.preview_map_definition(self.draft)
            self.topology_canvas.set_svg(self._topology_svg(definition), fit=True)
            self.validation_label.setText(
                f"Valid: {len(definition.territories)} territories, "
                f"{len(definition.adjacencies)} directed unit connections"
            )
            self.validation_label.setStyleSheet("color: #2f6843")
            self.yaml_editor.document().setModified(False)
            if not self.setup_editor.document().isModified():
                self._load_setup_editor()
            return True
        except Exception as exc:
            self.validation_label.setText(str(exc))
            self.validation_label.setStyleSheet("color: #8a302b")
            return False

    def _topology_svg(self, definition) -> bytes:
        root = ElementTree.fromstring(self._preview_svg_without())
        namespace = "http://www.w3.org/2000/svg"

        def tag(name: str) -> str:
            return f"{{{namespace}}}{name}"

        original_children = list(root)
        underlay = ElementTree.Element(tag("g"), {"id": "topology-map-underlay", "opacity": "0.58"})
        for child in original_children:
            if child.tag.rsplit("}", 1)[-1] not in {"defs", "style", "title", "desc"}:
                root.remove(child)
                underlay.append(child)
        root.append(underlay)

        defs = ElementTree.SubElement(root, tag("defs"))
        colours = {"army": "#f4511e", "fleet": "#00b8d4", "both": "#d500f9"}
        for name, colour in colours.items():
            marker = ElementTree.SubElement(
                defs,
                tag("marker"),
                {
                    "id": f"topology-arrow-{name}",
                    "viewBox": "0 0 10 10",
                    "refX": "8",
                    "refY": "5",
                    "markerWidth": "6",
                    "markerHeight": "6",
                    "orient": "auto-start-reverse",
                },
            )
            ElementTree.SubElement(
                marker,
                tag("path"),
                {"d": "M 0 0 L 10 5 L 0 10 z", "fill": colour},
            )

        def location_id(location: Location) -> str:
            return str(location.territory_id) + (
                f"/{location.coast_id}" if location.coast_id is not None else ""
            )

        directions: dict[tuple[str, str], set[UnitType]] = {}
        for edge in definition.adjacencies:
            origin = location_id(edge.origin)
            destination = location_id(edge.destination)
            if origin != destination:
                directions.setdefault((origin, destination), set()).add(edge.unit_type)
        by_id = {str(item.id): item for item in definition.territories}
        nodes: dict[str, tuple[Point, str, str, str]] = {}
        for territory in definition.territories:
            if territory.kind is TerritoryKind.LAND:
                point = definition.presentation.army_anchors.get(
                    territory.id, definition.presentation.label_anchors[territory.id]
                )
                anchor_type = "army"
            else:
                point = definition.presentation.fleet_anchors.get(
                    Location(territory.id), definition.presentation.label_anchors[territory.id]
                )
                anchor_type = "fleet"
            nodes[str(territory.id)] = (
                point,
                anchor_type,
                str(territory.id),
                territory.abbreviation,
            )
            for coast_id in territory.split_coast_ids:
                location = Location(territory.id, coast_id)
                nodes[location_id(location)] = (
                    definition.presentation.fleet_anchors[location],
                    "fleet",
                    str(territory.id),
                    f"{territory.abbreviation}/{coast_id}",
                )
        self._topology_nodes = {
            node_id: point
            for node_id, (point, _anchor_type, _territory_id, _label) in nodes.items()
        }
        self._topology_node_territories = {
            node_id: territory_id
            for node_id, (_point, _anchor_type, territory_id, _label) in nodes.items()
        }
        self._topology_names = {
            node_id: by_id[territory_id].name
            + (
                f" — {coast_label_text(CoastId(node_id.partition('/')[2]))}"
                if "/" in node_id
                else ""
            )
            for node_id, territory_id in self._topology_node_territories.items()
        }
        self._topology_hovered_territory = None

        edge_layer = ElementTree.SubElement(root, tag("g"), {"id": "topology-edges"})
        pairs = sorted({tuple(sorted(pair)) for pair in directions})
        for left, right in pairs:
            forward = directions.get((left, right), set())
            reverse = directions.get((right, left), set())
            variants = (
                [(left, right, forward, False)]
                if forward == reverse
                else [
                    (left, right, forward, True),
                    (right, left, reverse, True),
                ]
            )
            for origin, destination, units, directed in variants:
                if not units:
                    continue
                kind = (
                    "both" if units == {UnitType.ARMY, UnitType.FLEET} else next(iter(units)).value
                )
                origin_anchor = nodes[origin][0]
                destination_anchor = nodes[destination][0]
                attributes = {
                    "x1": str(origin_anchor.x),
                    "y1": str(origin_anchor.y),
                    "x2": str(destination_anchor.x),
                    "y2": str(destination_anchor.y),
                    "fill": "none",
                    "data-origin": origin,
                    "data-destination": destination,
                    "data-kind": kind,
                }
                halo = attributes | {
                    "stroke": "#263238",
                    "stroke-width": "5",
                    "stroke-opacity": "0.72",
                }
                ElementTree.SubElement(edge_layer, tag("line"), halo)
                attributes |= {
                    "stroke": colours[kind],
                    "stroke-width": "2.4",
                    "stroke-opacity": "0.96",
                }
                if directed:
                    attributes["marker-end"] = f"url(#topology-arrow-{kind})"
                ElementTree.SubElement(edge_layer, tag("line"), attributes)

        node_layer = ElementTree.SubElement(root, tag("g"), {"id": "topology-nodes"})
        for node_id, (point, anchor_type, territory_id, node_label) in sorted(nodes.items()):
            ElementTree.SubElement(
                node_layer,
                tag("circle"),
                {
                    "cx": str(point.x),
                    "cy": str(point.y),
                    "r": "4.5",
                    "fill": "#ffcc80" if anchor_type == "army" else "#80deea",
                    "stroke": "#263238",
                    "stroke-width": "1.8",
                    "data-territory": territory_id,
                    "data-location": node_id,
                    "data-anchor-type": anchor_type,
                },
            )
            label = ElementTree.SubElement(
                node_layer,
                tag("text"),
                {
                    "x": str(point.x + 6),
                    "y": str(point.y - 6),
                    "font-size": "11",
                    "font-weight": "600",
                    "fill": "#111111",
                },
            )
            label.text = node_label
        return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)

    def _topology_hovered(self, x: float, y: float) -> None:
        if not self._topology_nodes:
            return
        node_id, point = min(
            self._topology_nodes.items(),
            key=lambda item: math.hypot(item[1].x - x, item[1].y - y),
        )
        scale = max(abs(self.topology_canvas.transform().m11()), 0.01)
        if math.hypot(point.x - x, point.y - y) > 16 / scale:
            self.topology_canvas.setToolTip("")
            self._topology_hovered_territory = None
            return
        if node_id == self._topology_hovered_territory:
            return
        territory_id = self._topology_node_territories[node_id]
        if self._highlight_yaml_territory(territory_id):
            self._topology_hovered_territory = node_id
            name = self._topology_names.get(node_id, node_id)
            self.topology_canvas.setToolTip(
                f"{name}: edit this highlighted YAML block, including split_coasts."
            )

    def _highlight_yaml_territory(self, territory_id: str) -> bool:
        text = self.yaml_editor.toPlainText()
        start = re.search(rf"(?m)^  {re.escape(territory_id)}:\s*$", text)
        if start is None:
            return False
        next_section = re.search(
            r"(?m)^(?:  [^\s][^:\n]*|[^\s#][^:\n]*):\s*$",
            text[start.end() :],
        )
        end = start.end() + next_section.start() if next_section is not None else len(text)

        highlight_cursor = QTextCursor(self.yaml_editor.document())
        highlight_cursor.setPosition(start.start())
        highlight_cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        selection = QTextEdit.ExtraSelection()
        selection.cursor = highlight_cursor  # type: ignore[attr-defined]
        selection.format.setBackground(QColor("#f2d98d"))  # type: ignore[attr-defined]
        selection.format.setProperty(  # type: ignore[attr-defined]
            QTextFormat.Property.FullWidthSelection, True
        )
        self.yaml_editor.setExtraSelections([selection])

        navigation_cursor = QTextCursor(self.yaml_editor.document())
        navigation_cursor.setPosition(start.start() + 2)
        self.yaml_editor.setTextCursor(navigation_cursor)
        self.yaml_editor.centerCursor()
        return True

    def _reload_anchor_scene(self) -> None:
        self.anchor_canvas.set_svg(
            self._preview_svg_without(
                "territory-labels",
                "coast-labels",
                "supply-centres",
                "units",
                "orders",
            ),
            fit=True,
        )
        self._selected_coast_label = None
        self._coast_label_items.clear()
        self.coast_rotation.setEnabled(False)
        presentation = self.draft.presentation
        territories = {territory.id: territory for territory in self.draft.territories}
        label_mode = self.placement_labels.currentData()
        if not self.game_placement_only:
            if label_mode != "full":
                self._selected_territory_label = None
                self.display_name_editor.clear()
                self.display_name_group.setEnabled(False)
            elif self._selected_territory_label is not None:
                selected = territories[self._selected_territory_label]
                self.display_name_editor.setPlainText(selected.display_name)
                self.display_name_group.setEnabled(True)
        if label_mode:
            anchor_type = "label" if label_mode == "full" else "abbreviation"
            anchors = (
                presentation.label_anchors
                if label_mode == "full"
                else presentation.abbreviation_anchors
            )
            for territory, point in anchors.items():
                definition = territories[territory]
                text = definition.display_name if label_mode == "full" else definition.abbreviation
                item = TextAnchorItem(
                    point,
                    text,
                    self.draft.presentation.label_colour,
                    lambda new_point, territory=territory, anchor_type=anchor_type: (
                        self._anchor_moved(
                            territory,
                            anchor_type,
                            None,
                            new_point,
                        )
                    ),
                    size=presentation.territory_label_font_size,
                    bold=True,
                    selection_callback=(
                        (lambda territory=territory: self._select_territory_label(territory))
                        if label_mode == "full" and not self.game_placement_only
                        else None
                    ),
                )
                item.setToolTip(f"{definition.name}: {label_mode} label")
                self.anchor_canvas.scene().addItem(item)
        if self.coast_labels_preview.isChecked():
            for location, point in presentation.coast_label_anchors.items():
                if location.coast_id is None:
                    continue
                item = TextAnchorItem(
                    point,
                    coast_label_text(location.coast_id),
                    self.draft.presentation.label_colour,
                    lambda new_point, location=location: self._anchor_moved(
                        location.territory_id,
                        "coast_label",
                        str(location.coast_id),
                        new_point,
                    ),
                    size=presentation.coast_label_font_size,
                    bold=True,
                    italic=True,
                    rotation=presentation.coast_label_rotations.get(location, 0),
                    selection_callback=lambda location=location: self._select_coast_label(location),
                )
                item.setToolTip(
                    f"{territories[location.territory_id].name}: "
                    f"{coast_label_text(location.coast_id)} — drag, then set rotation"
                )
                self._coast_label_items[location] = item
                self.anchor_canvas.scene().addItem(item)
        if self.supply_preview.isChecked():
            powers = {power.id: power for power in self.draft.powers}
            owners = self.draft.default_starting_setup.state.supply_centre_owners
            for territory, point in presentation.supply_centre_anchors.items():
                owner = owners.get(territory)
                colour = (
                    darken_colour(powers[owner].colour, 0.82)
                    if owner is not None and owner in powers
                    else "#eee6c8"
                )
                centre_item = SupplyCentreAnchorItem(
                    point,
                    colour,
                    lambda new_point, territory=territory: self._anchor_moved(
                        territory, "supply_centre", None, new_point
                    ),
                )
                centre_item.setToolTip(f"{territories[territory].name}: supply centre")
                self.anchor_canvas.scene().addItem(centre_item)
        if self.armies_preview.isChecked():
            unit_entries: list[tuple[Any, str, str | None, Any]] = [
                (territory, "army", None, point)
                for territory, point in presentation.army_anchors.items()
            ]
            self._add_unit_previews(
                unit_entries,
                DEFAULT_ARMY_SVG,
                UnitType.ARMY,
                "#3f7b53",
            )
        if self.fleets_preview.isChecked():
            unit_entries = [
                (
                    location.territory_id,
                    "fleet",
                    str(location.coast_id) if location.coast_id else None,
                    point,
                )
                for location, point in presentation.fleet_anchors.items()
            ]
            asset = DEFAULT_FLEET_SVG
            colour = "#356f95"
            self._add_unit_previews(unit_entries, asset, UnitType.FLEET, colour)

    def _add_unit_previews(
        self, unit_entries, asset: bytes, unit_type: UnitType, fallback_colour: str
    ) -> None:
        state = self.draft.default_starting_setup.state
        powers = {power.id: power for power in self.draft.powers}
        starting_units = {(unit.unit_type, unit.location): unit.power_id for unit in state.units}
        for territory, anchor, coast, point in unit_entries:
            location = Location(territory, CoastId(coast) if coast is not None else None)
            power_id = starting_units.get((unit_type, location))
            if power_id is None:
                power_id = state.territory_controllers.get(territory)
            colour = (
                darken_colour(powers[power_id].colour, 0.82)
                if power_id is not None and power_id in powers
                else fallback_colour
            )
            unit_item = UnitAnchorItem(
                point,
                embedded_unit_svg(asset, colour),
                lambda new_point, territory=territory, anchor=anchor, coast=coast: (
                    self._anchor_moved(territory, anchor, coast, new_point)
                ),
            )
            if (unit_type, location) not in starting_units:
                unit_item.setOpacity(0.68)
            unit_item.setToolTip(f"{territory}: {anchor}" + (f" ({coast})" if coast else ""))
            self.anchor_canvas.scene().addItem(unit_item)

    def _preview_changed(self, checked: bool) -> None:
        del checked
        self._reload_anchor_scene()

    def _label_font_sizes_changed(self, value: float) -> None:
        del value
        try:
            self.draft = self.service.update_map_label_font_sizes(
                self.draft,
                self.territory_font_size.value(),
                self.coast_font_size.value(),
            )
            if not self.game_placement_only:
                self.yaml_editor.setPlainText(self.draft.map_yaml)
            self._reload_anchor_scene()
        except Exception as exc:
            self._show_error(f"Could not change label sizes: {exc}")

    def _refresh_colour_buttons(self) -> None:
        presentation = self.draft.presentation
        for label, colour, button in (
            ("Text", presentation.label_colour, self.label_colour_button),
            (
                "Inaccessible",
                presentation.inaccessible_region_colour,
                self.inaccessible_colour_button,
            ),
            ("Sea", presentation.sea_colour, self.sea_colour_button),
            ("Unclaimed", presentation.unclaimed_region_colour, self.unclaimed_colour_button),
        ):
            foreground = "#171714" if QColor(colour).lightness() >= 145 else "#fffdf7"
            button.setText(f"{label} {colour.upper()}")
            button.setStyleSheet(
                f"QPushButton {{ background: {colour}; color: {foreground}; "
                "border: 1px solid #625d50; }"
            )

    def _choose_map_colour(self, field: str) -> None:
        current = getattr(self.draft.presentation, field)
        label = field.removesuffix("_colour").replace("_", " ").title()
        selected = QColorDialog.getColor(QColor(current), self, f"Choose {label}")
        if selected.isValid():
            self._set_map_colour(field, selected.name())

    def _set_map_colour(self, field: str, colour: str) -> None:
        values = {
            "label_colour": self.draft.presentation.label_colour,
            "inaccessible_region_colour": self.draft.presentation.inaccessible_region_colour,
            "sea_colour": self.draft.presentation.sea_colour,
            "unclaimed_region_colour": self.draft.presentation.unclaimed_region_colour,
        }
        if field not in values:
            self._show_error(f"Unknown map colour: {field}")
            return
        values[field] = colour
        try:
            self.draft = self.service.update_map_colours(
                self.draft,
                values["label_colour"],
                values["inaccessible_region_colour"],
                values["sea_colour"],
                values["unclaimed_region_colour"],
            )
            if not self.game_placement_only:
                self.yaml_editor.setPlainText(self.draft.map_yaml)
            self._refresh_colour_buttons()
            self._reload_setup_preview()
            self._reload_anchor_scene()
        except Exception as exc:
            self._show_error(f"Could not change map colour: {exc}")

    def _select_territory_label(self, territory_id) -> None:
        if self.game_placement_only:
            return
        territory = next(item for item in self.draft.territories if item.id == territory_id)
        self._selected_territory_label = territory_id
        self.display_name_editor.setPlainText(territory.display_name)
        self.display_name_group.setEnabled(True)

    def _apply_display_name(self) -> None:
        territory_id = self._selected_territory_label
        if territory_id is None or self.game_placement_only:
            return
        try:
            self.draft = self.service.update_map_territory_display_name(
                self.draft, territory_id, self.display_name_editor.toPlainText()
            )
            self.yaml_editor.setPlainText(self.draft.map_yaml)
            self._reload_anchor_scene()
        except Exception as exc:
            self._show_error(f"Could not change display name: {exc}")

    def _select_coast_label(self, location: Location) -> None:
        self._selected_coast_label = location
        self.coast_rotation.blockSignals(True)
        self.coast_rotation.setValue(
            round(self.draft.presentation.coast_label_rotations.get(location, 0))
        )
        self.coast_rotation.blockSignals(False)
        self.coast_rotation.setEnabled(True)

    def _clear_label_selection(self) -> None:
        self._selected_coast_label = None
        self.coast_rotation.setEnabled(False)
        self._selected_territory_label = None
        if not self.game_placement_only:
            self.display_name_editor.clear()
            self.display_name_group.setEnabled(False)

    def _coast_rotation_changed(self, rotation: int) -> None:
        location = self._selected_coast_label
        if location is None or location.coast_id is None:
            return
        try:
            self.draft = self.service.update_map_coast_label_rotation(
                self.draft,
                location.territory_id,
                str(location.coast_id),
                rotation,
            )
            if not self.game_placement_only:
                self.yaml_editor.setPlainText(self.draft.map_yaml)
            item = self._coast_label_items.get(location)
            if item is not None:
                item.setRotation(rotation)
        except Exception as exc:
            self._show_error(f"Could not rotate coast label: {exc}")

    def _anchor_moved(self, territory, anchor, coast, point) -> None:
        try:
            self.draft = self.service.update_map_anchor(self.draft, territory, anchor, point, coast)
            if not self.game_placement_only:
                self.yaml_editor.setPlainText(self.draft.map_yaml)
        except Exception as exc:
            self._show_error(f"Could not move anchor: {exc}")

    def _load_setup_editor(self) -> None:
        document = yaml.safe_load(self.draft.map_yaml)
        if not isinstance(document, dict):
            return
        setup = {
            "start": document.get("start", {}),
            "teams": document.get("teams", {}),
        }
        self.setup_editor.setPlainText(yaml.safe_dump(setup, sort_keys=False, allow_unicode=True))
        self.setup_editor.document().setModified(False)

    def _reload_setup_preview(self) -> bool:
        try:
            scene = self.service.preview_map_setup(self.draft)
            self.setup_canvas.set_scene(scene, fit=True)
            return True
        except Exception as exc:
            self.setup_validation_label.setText(f"Could not render setup: {exc}")
            self.setup_validation_label.setStyleSheet("color: #8a302b")
            return False

    def _focus_topology_section(self) -> None:
        cursor = self.yaml_editor.document().find("territories:")
        if not cursor.isNull():
            self.yaml_editor.setTextCursor(cursor)
            self.yaml_editor.ensureCursorVisible()

    def _apply_setup_changes(self) -> bool:
        try:
            setup = yaml.safe_load(self.setup_editor.toPlainText())
            if not isinstance(setup, dict):
                raise ValueError("Setup YAML must contain a mapping")
            unexpected = set(setup) - {"start", "teams"}
            if unexpected:
                raise ValueError("Powers and setup accepts only 'start' and 'teams' sections")
            if not isinstance(setup.get("start"), dict) or not isinstance(setup.get("teams"), dict):
                raise ValueError("Both 'start' and 'teams' must be mappings")
            document = yaml.safe_load(self.yaml_editor.toPlainText())
            if not isinstance(document, dict):
                raise ValueError("Map YAML must contain a mapping")
            document["start"] = setup["start"]
            document["teams"] = setup["teams"]
            text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
            self.yaml_editor.setPlainText(text)
            self.draft = replace(self.draft, map_yaml=text)
            self.setup_editor.document().setModified(False)
            if not self._validate():
                self.setup_validation_label.setText("Map validation failed")
                self.setup_validation_label.setStyleSheet("color: #8a302b")
                return False
            if not self._reload_setup_preview():
                return False
            self.setup_validation_label.setText("Map preview regenerated")
            self.setup_validation_label.setStyleSheet("color: #2f6843")
            return True
        except Exception as exc:
            self.setup_validation_label.setText(str(exc))
            self.setup_validation_label.setStyleSheet("color: #8a302b")
            return False

    def _tab_changed(self, index: int) -> None:
        if (
            index != 2
            and self.setup_editor.document().isModified()
            and not self._apply_setup_changes()
        ):
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(2)
            self.tabs.blockSignals(False)
            return
        if index == 1:
            self._validate()
        elif self.yaml_editor.document().isModified():
            if self._validate():
                if index == 0:
                    self._reload_classification_preview()
                elif index == 2:
                    self._reload_setup_preview()
                elif index == 3:
                    self._reload_anchor_scene()
        elif index == 0:
            self._reload_classification_preview()
        elif index == 2:
            self._load_setup_editor()
            self._reload_setup_preview()
        elif index == 3:
            self._reload_anchor_scene()

    def _show_error(self, text: str) -> None:
        self.message.setText(text)
        self.message.setStyleSheet("color: #8a302b")
        self.message.setVisible(True)

    def _save(self) -> None:
        if self.game_placement_only:
            try:
                self.saved_definition = self.service.save_game_map_placement(self.draft)
                self.saved.emit(self.saved_definition)
            except Exception as exc:
                self._show_error(f"Could not save game map placement: {exc}")
            return
        if self.setup_editor.document().isModified() and not self._apply_setup_changes():
            self.tabs.setCurrentIndex(2)
            return
        if not self._validate():
            self.tabs.setCurrentIndex(1)
            return
        try:
            self.saved_definition = self.service.save_map_draft(self.draft)
            self.saved.emit(self.saved_definition)
        except Exception as exc:
            self._show_error(f"Could not save map: {exc}")
