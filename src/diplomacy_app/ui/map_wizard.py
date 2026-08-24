"""Tabbed custom SVG map configuration editor."""

from __future__ import annotations

import base64
import math
import re
from dataclasses import replace
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import yaml
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCursor, QTextDocument, QTextFormat
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
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
    Location,
    MapDraft,
    Point,
    SvgElementRole,
    TerritoryKind,
    UnitType,
)
from diplomacy_app.map_library.defaults import DEFAULT_ARMY_SVG, DEFAULT_FLEET_SVG
from diplomacy_app.map_library.svg_importer import territory_geometries
from diplomacy_app.presentation import coast_label_text
from diplomacy_app.ui.map_canvas import (
    MapCanvas,
    MapZoomControls,
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
        self.query.setStyleSheet("" if found else "QLineEdit { background: #f4d8d3; }")


class MapWizard(QWidget):
    cancelled = Signal()
    saved = Signal(object)

    def __init__(self, service, draft: MapDraft, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.draft = draft
        self.saved_definition = None
        self._element_geometries = territory_geometries(draft.svg, draft.element_roles)
        self._row_by_element: dict[str, int] = {}
        self._topology_nodes: dict[str, Point] = {}
        self._topology_names: dict[str, str] = {}
        self._topology_hovered_territory: str | None = None
        self._selected_coast_label: Location | None = None
        self._coast_label_items: dict[Location, TextAnchorItem] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(3)
        self.outer_layout = layout
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._build_classification_tab()
        self._build_yaml_tab()
        self._build_setup_tab()
        self._build_anchor_tab()
        self._build_assets_tab()
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
        self.save_button = QPushButton("Save configured map")
        self.save_button.setProperty("primary", True)
        self.save_button.clicked.connect(self._save)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self.yaml_editor.setPlainText(draft.map_yaml)
        self._populate_roles()
        self._reload_anchor_scene()
        self.tabs.currentChanged.connect(self._tab_changed)
        self._validate()
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
        self.roles.setHorizontalHeaderLabels(["Territory", "SVG element", "Role"])
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
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(3)
        self.setup_editor = QPlainTextEdit()
        self.setup_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setup_find = YamlFindBar(self.setup_editor, page)
        layout.addWidget(self.setup_find)
        layout.addWidget(self.setup_editor, 1)
        controls = QHBoxLayout()
        apply_setup = QPushButton("Apply to map YAML")
        apply_setup.clicked.connect(self._apply_setup_changes)
        controls.addWidget(apply_setup)
        self.setup_validation_label = QLabel()
        self.setup_validation_label.setWordWrap(True)
        controls.addWidget(self.setup_validation_label, 1)
        layout.addLayout(controls)
        self.tabs.addTab(page, "Powers and setup")

    def _build_anchor_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)
        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("Show"))
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
        preview_row.addWidget(self.armies_preview)
        preview_row.addWidget(self.fleets_preview)
        preview_row.addWidget(self.supply_preview)
        preview_row.addWidget(self.coast_labels_preview)
        preview_row.addWidget(QLabel("Labels"))
        self.placement_labels = QComboBox()
        self.placement_labels.addItem("None", None)
        self.placement_labels.addItem("Full names", "full")
        self.placement_labels.addItem("Abbreviations", "abbreviation")
        self.placement_labels.setCurrentIndex(1)
        self.placement_labels.currentIndexChanged.connect(self._reload_anchor_scene)
        preview_row.addWidget(self.placement_labels)
        preview_row.addWidget(QLabel("Coast rotation"))
        self.coast_rotation = QSpinBox()
        self.coast_rotation.setRange(-180, 180)
        self.coast_rotation.setSingleStep(5)
        self.coast_rotation.setSuffix("°")
        self.coast_rotation.setFixedWidth(74)
        self.coast_rotation.setEnabled(False)
        self.coast_rotation.valueChanged.connect(self._coast_rotation_changed)
        preview_row.addWidget(self.coast_rotation)
        preview_row.addStretch()
        layout.addLayout(preview_row)
        self.anchor_canvas = MapCanvas()
        layout.addWidget(self.anchor_canvas, 1)
        self.placement_zoom = MapZoomControls(self.anchor_canvas)
        self.tabs.addTab(page, "Placement")

    def _build_assets_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(3)
        previews = QHBoxLayout()
        previews.addStretch()
        army_column = QVBoxLayout()
        self.army_preview_label = QLabel()
        army_column.addWidget(self.army_preview_label)
        self.army_asset_preview = MapCanvas()
        self.army_asset_preview.setFixedSize(340, 240)
        army_column.addWidget(self.army_asset_preview)
        self.army_asset_zoom = MapZoomControls(self.army_asset_preview)
        army = QPushButton("Choose army SVG…")
        army.clicked.connect(lambda: self._choose_asset("army"))
        army_column.addWidget(army)
        fleet_column = QVBoxLayout()
        self.fleet_preview_label = QLabel()
        fleet_column.addWidget(self.fleet_preview_label)
        self.fleet_asset_preview = MapCanvas()
        self.fleet_asset_preview.setFixedSize(340, 240)
        fleet_column.addWidget(self.fleet_asset_preview)
        self.fleet_asset_zoom = MapZoomControls(self.fleet_asset_preview)
        fleet = QPushButton("Choose fleet SVG…")
        fleet.clicked.connect(lambda: self._choose_asset("fleet"))
        fleet_column.addWidget(fleet)
        previews.addLayout(army_column)
        previews.addSpacing(12)
        previews.addLayout(fleet_column)
        previews.addStretch()
        layout.addLayout(previews)
        layout.addStretch()
        self.tabs.addTab(page, "Unit symbols")
        self._update_asset_status()

    def _populate_roles(self) -> None:
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
            self.roles.setItem(row, 0, QTableWidgetItem(display_name))
            self.roles.setItem(row, 1, QTableWidgetItem(element_id))
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
            self._reload_anchor_scene()
        except Exception as exc:
            self._show_error(f"Could not change region role: {exc}")

    def _commit_editor(self) -> None:
        self.draft = replace(self.draft, map_yaml=self.yaml_editor.toPlainText())

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
        root = ElementTree.fromstring(definition.assets.map_svg)
        namespace = "http://www.w3.org/2000/svg"

        def tag(name: str) -> str:
            return f"{{{namespace}}}{name}"

        original_children = list(root)
        underlay = ElementTree.Element(tag("g"), {"id": "topology-map-underlay", "opacity": "0.34"})
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
        directions: dict[tuple[str, str], set[UnitType]] = {}
        for edge in definition.adjacencies:
            origin = str(edge.origin.territory_id)
            destination = str(edge.destination.territory_id)
            if origin != destination:
                directions.setdefault((origin, destination), set()).add(edge.unit_type)
        by_id = {str(item.id): item for item in definition.territories}
        nodes = {}
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
            nodes[str(territory.id)] = (point, anchor_type)
        self._topology_nodes = {
            territory_id: point for territory_id, (point, _anchor_type) in nodes.items()
        }
        self._topology_names = {
            str(territory.id): territory.name for territory in definition.territories
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
        for territory_id, (point, anchor_type) in sorted(nodes.items()):
            territory = by_id[territory_id]
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
            label.text = territory.abbreviation
        coast_label_layer = ElementTree.SubElement(root, tag("g"), {"id": "topology-coast-labels"})
        for location, point in sorted(
            definition.presentation.coast_label_anchors.items(),
            key=lambda item: (item[0].territory_id, item[0].coast_id or ""),
        ):
            if location.coast_id is None:
                continue
            rotation = definition.presentation.coast_label_rotations.get(location, 0)
            coast_label = ElementTree.SubElement(
                coast_label_layer,
                tag("text"),
                {
                    "x": str(point.x),
                    "y": str(point.y),
                    "text-anchor": "middle",
                    "dominant-baseline": "central",
                    "font-family": "Georgia, serif",
                    "font-size": "10",
                    "font-style": "italic",
                    "font-weight": "600",
                    "fill": "#111111",
                    "transform": f"rotate({rotation:g} {point.x:g} {point.y:g})",
                    "data-location": f"{location.territory_id}/{location.coast_id}",
                },
            )
            coast_label.text = coast_label_text(location.coast_id)
        return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)

    def _topology_hovered(self, x: float, y: float) -> None:
        if not self._topology_nodes:
            return
        territory_id, point = min(
            self._topology_nodes.items(),
            key=lambda item: math.hypot(item[1].x - x, item[1].y - y),
        )
        scale = max(abs(self.topology_canvas.transform().m11()), 0.01)
        if math.hypot(point.x - x, point.y - y) > 16 / scale:
            self.topology_canvas.setToolTip("")
            self._topology_hovered_territory = None
            return
        if territory_id == self._topology_hovered_territory:
            return
        if self._highlight_yaml_territory(territory_id):
            self._topology_hovered_territory = territory_id
            name = self._topology_names.get(territory_id, territory_id)
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
        self.anchor_canvas.set_svg(self.draft.svg, fit=True)
        self._selected_coast_label = None
        self._coast_label_items.clear()
        self.coast_rotation.setEnabled(False)
        presentation = self.draft.presentation
        territories = {territory.id: territory for territory in self.draft.territories}
        label_mode = self.placement_labels.currentData()
        if label_mode:
            for territory, point in presentation.label_anchors.items():
                definition = territories[territory]
                text = definition.name if label_mode == "full" else definition.abbreviation
                item = TextAnchorItem(
                    point,
                    text,
                    "#4c3b1e",
                    lambda new_point, territory=territory: self._anchor_moved(
                        territory, "label", None, new_point
                    ),
                    bold=True,
                )
                item.setToolTip(f"{definition.name}: label")
                self.anchor_canvas.scene().addItem(item)
        if self.coast_labels_preview.isChecked():
            for location, point in presentation.coast_label_anchors.items():
                if location.coast_id is None:
                    continue
                item = TextAnchorItem(
                    point,
                    coast_label_text(location.coast_id),
                    "#171714",
                    lambda new_point, location=location: self._anchor_moved(
                        location.territory_id,
                        "coast_label",
                        str(location.coast_id),
                        new_point,
                    ),
                    size=10,
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
            for territory, point in presentation.supply_centre_anchors.items():
                item = TextAnchorItem(
                    point,
                    "★",
                    "#eee6c8",
                    lambda new_point, territory=territory: self._anchor_moved(
                        territory, "supply_centre", None, new_point
                    ),
                    size=18,
                )
                item.setToolTip(f"{territories[territory].name}: supply centre")
                self.anchor_canvas.scene().addItem(item)
        if self.armies_preview.isChecked():
            unit_entries: list[tuple[Any, str, str | None, Any]] = [
                (territory, "army", None, point)
                for territory, point in presentation.army_anchors.items()
            ]
            self._add_unit_previews(
                unit_entries,
                self.draft.army_svg or DEFAULT_ARMY_SVG,
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
            asset = self.draft.fleet_svg or DEFAULT_FLEET_SVG
            colour = "#356f95"
            self._add_unit_previews(unit_entries, asset, colour)

    def _add_unit_previews(self, unit_entries, asset: bytes, colour: str) -> None:
        tinted_asset = asset.replace(b"currentColor", colour.encode())
        for territory, anchor, coast, point in unit_entries:
            unit_item = UnitAnchorItem(
                point,
                tinted_asset,
                lambda new_point, territory=territory, anchor=anchor, coast=coast: (
                    self._anchor_moved(territory, anchor, coast, new_point)
                ),
            )
            unit_item.setToolTip(f"{territory}: {anchor}" + (f" ({coast})" if coast else ""))
            self.anchor_canvas.scene().addItem(unit_item)

    def _preview_changed(self, checked: bool) -> None:
        del checked
        self._reload_anchor_scene()

    def _select_coast_label(self, location: Location) -> None:
        self._selected_coast_label = location
        self.coast_rotation.blockSignals(True)
        self.coast_rotation.setValue(
            round(self.draft.presentation.coast_label_rotations.get(location, 0))
        )
        self.coast_rotation.blockSignals(False)
        self.coast_rotation.setEnabled(True)

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
            self.yaml_editor.setPlainText(self.draft.map_yaml)
            item = self._coast_label_items.get(location)
            if item is not None:
                item.setRotation(rotation)
        except Exception as exc:
            self._show_error(f"Could not rotate coast label: {exc}")

    def _anchor_moved(self, territory, anchor, coast, point) -> None:
        try:
            self.draft = self.service.update_map_anchor(self.draft, territory, anchor, point, coast)
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
            self.setup_validation_label.setText("Applied to map YAML")
            self.setup_validation_label.setStyleSheet("color: #2f6843")
            return True
        except Exception as exc:
            self.setup_validation_label.setText(str(exc))
            self.setup_validation_label.setStyleSheet("color: #8a302b")
            return False

    def _choose_asset(self, kind: str) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, f"Choose {kind} SVG", "", "SVG files (*.svg)"
        )
        if not filename:
            return
        data = Path(filename).read_bytes()
        self.draft = replace(
            self.draft,
            army_svg=data if kind == "army" else self.draft.army_svg,
            fleet_svg=data if kind == "fleet" else self.draft.fleet_svg,
        )
        self._update_asset_status()
        self._reload_anchor_scene()

    def _update_asset_status(self) -> None:
        army = self.draft.army_svg or DEFAULT_ARMY_SVG
        fleet = self.draft.fleet_svg or DEFAULT_FLEET_SVG
        self.army_preview_label.setText(
            "Army — custom symbol" if self.draft.army_svg else "Army — supplied default"
        )
        self.fleet_preview_label.setText(
            "Fleet — custom symbol" if self.draft.fleet_svg else "Fleet — supplied default"
        )
        self.army_asset_preview.set_svg(self._asset_preview_svg(army), fit=True)
        self.fleet_asset_preview.set_svg(self._asset_preview_svg(fleet), fit=True)

    @staticmethod
    def _asset_preview_svg(asset: bytes) -> bytes:
        encoded = base64.b64encode(asset.replace(b"currentColor", b"#344d40")).decode()
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 220">
          <path d="M35 38 Q110 15 180 34 T285 48 L272 190 Q170 208 48 182 Z"
                fill="#d0c9aa" stroke="#665f4f" stroke-width="2"/>
          <image x="144" y="99" width="32" height="22"
                 href="data:image/svg+xml;base64,{encoded}"/>
        </svg>""".encode()

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
            if self._validate() and index == 3:
                self._reload_anchor_scene()
        elif index == 2:
            self._load_setup_editor()
        elif index == 3:
            self._reload_anchor_scene()

    def _show_error(self, text: str) -> None:
        self.message.setText(text)
        self.message.setStyleSheet("color: #8a302b")
        self.message.setVisible(True)

    def _save(self) -> None:
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
