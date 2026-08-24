"""Tabbed custom SVG map configuration editor."""

from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from shapely.geometry import Point as GeometryPoint

from diplomacy_app.domain.models import (
    Location,
    MapDraft,
    SvgElementRole,
    TerritoryKind,
    UnitType,
)
from diplomacy_app.map_library.defaults import DEFAULT_ARMY_SVG, DEFAULT_FLEET_SVG
from diplomacy_app.map_library.svg_importer import territory_geometries
from diplomacy_app.ui.map_canvas import (
    MapCanvas,
    MapZoomControls,
    TextAnchorItem,
    UnitAnchorItem,
)


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
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._build_classification_tab()
        self._build_yaml_tab()
        self._build_anchor_tab()
        self._build_assets_tab()
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setVisible(False)
        layout.addWidget(self.message)
        buttons = QHBoxLayout()
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

    def _build_classification_tab(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
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
        splitter.addWidget(map_side)
        splitter.addWidget(self.roles)
        splitter.setSizes([720, 330])
        layout.addWidget(splitter)
        self.tabs.addTab(page, "SVG regions")

    def _build_yaml_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        legend = QLabel(
            '<span style="color:#f4511e; font-weight:700">━━ Army</span>&nbsp;&nbsp; '
            '<span style="color:#00b8d4; font-weight:700">━━ Fleet</span>&nbsp;&nbsp; '
            '<span style="color:#d500f9; font-weight:700">━━ Both</span>&nbsp;&nbsp; '
            "→ one-way &nbsp;&nbsp; ○ node"
        )
        layout.addWidget(legend)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.yaml_editor = QPlainTextEdit()
        self.yaml_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.topology_canvas = MapCanvas()
        topology_side = QWidget()
        topology_layout = QVBoxLayout(topology_side)
        topology_layout.setContentsMargins(0, 0, 0, 0)
        topology_layout.addWidget(self.topology_canvas, 1)
        self.topology_zoom = MapZoomControls(self.topology_canvas)
        splitter.addWidget(self.yaml_editor)
        splitter.addWidget(topology_side)
        splitter.setSizes([650, 430])
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

    def _build_anchor_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("Show"))
        self.armies_preview = QCheckBox("Armies")
        self.fleets_preview = QCheckBox("Fleets")
        self.supply_preview = QCheckBox("Supply centres")
        self.armies_preview.setChecked(True)
        self.armies_preview.toggled.connect(self._preview_changed)
        self.fleets_preview.toggled.connect(self._preview_changed)
        self.supply_preview.setChecked(True)
        self.supply_preview.toggled.connect(self._preview_changed)
        preview_row.addWidget(self.armies_preview)
        preview_row.addWidget(self.fleets_preview)
        preview_row.addWidget(self.supply_preview)
        preview_row.addWidget(QLabel("Labels"))
        self.placement_labels = QComboBox()
        self.placement_labels.addItem("None", None)
        self.placement_labels.addItem("Full names", "full")
        self.placement_labels.addItem("Abbreviations", "abbreviation")
        self.placement_labels.setCurrentIndex(1)
        self.placement_labels.currentIndexChanged.connect(self._reload_anchor_scene)
        preview_row.addWidget(self.placement_labels)
        preview_row.addStretch()
        layout.addLayout(preview_row)
        self.anchor_canvas = MapCanvas()
        layout.addWidget(self.anchor_canvas, 1)
        self.placement_zoom = MapZoomControls(self.anchor_canvas)
        self.tabs.addTab(page, "Placement")

    def _build_assets_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        previews = QHBoxLayout()
        army_column = QVBoxLayout()
        self.army_preview_label = QLabel()
        army_column.addWidget(self.army_preview_label)
        self.army_asset_preview = MapCanvas()
        army_column.addWidget(self.army_asset_preview)
        self.army_asset_zoom = MapZoomControls(self.army_asset_preview)
        fleet_column = QVBoxLayout()
        self.fleet_preview_label = QLabel()
        fleet_column.addWidget(self.fleet_preview_label)
        self.fleet_asset_preview = MapCanvas()
        fleet_column.addWidget(self.fleet_asset_preview)
        self.fleet_asset_zoom = MapZoomControls(self.fleet_asset_preview)
        previews.addLayout(army_column)
        previews.addLayout(fleet_column)
        layout.addLayout(previews, 1)
        army = QPushButton("Choose army SVG…")
        fleet = QPushButton("Choose fleet SVG…")
        army.clicked.connect(lambda: self._choose_asset("army"))
        fleet.clicked.connect(lambda: self._choose_asset("fleet"))
        layout.addWidget(army)
        layout.addWidget(fleet)
        self.asset_status = QLabel()
        layout.addWidget(self.asset_status)
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
                    "y": str(point.y - 5),
                    "font-size": "8",
                    "font-weight": "700",
                    "fill": "#1b1f1d",
                    "stroke": "#fffdf5",
                    "stroke-width": "2",
                    "paint-order": "stroke",
                },
            )
            label.text = territory.abbreviation
        return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)

    def _reload_anchor_scene(self) -> None:
        self.anchor_canvas.set_svg(self.draft.svg, fit=True)
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

    def _anchor_moved(self, territory, anchor, coast, point) -> None:
        try:
            self.draft = self.service.update_map_anchor(self.draft, territory, anchor, point, coast)
            self.yaml_editor.setPlainText(self.draft.map_yaml)
        except Exception as exc:
            self._show_error(f"Could not move anchor: {exc}")

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
        self.asset_status.setText(
            f"Army: {'custom' if self.draft.army_svg else 'default'}    "
            f"Fleet: {'custom' if self.draft.fleet_svg else 'default'}"
        )
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
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 140">
          <path d="M15 18 Q70 2 125 18 T205 25 L198 122 Q120 138 22 118 Z"
                fill="#d0c9aa" stroke="#665f4f" stroke-width="2"/>
          <image x="94" y="59" width="32" height="22"
                 href="data:image/svg+xml;base64,{encoded}"/>
        </svg>""".encode()

    def _tab_changed(self, index: int) -> None:
        if index == 1:
            self._validate()
        elif self.yaml_editor.document().isModified():
            if self._validate() and index == 2:
                self._reload_anchor_scene()
        elif index == 2:
            self._reload_anchor_scene()

    def _show_error(self, text: str) -> None:
        self.message.setText(text)
        self.message.setStyleSheet("color: #8a302b")
        self.message.setVisible(True)

    def _save(self) -> None:
        if not self._validate():
            self.tabs.setCurrentIndex(1)
            return
        try:
            self.saved_definition = self.service.save_map_draft(self.draft)
            self.saved.emit(self.saved_definition)
        except Exception as exc:
            self._show_error(f"Could not save map: {exc}")
