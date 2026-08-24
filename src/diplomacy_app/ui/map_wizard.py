"""Custom SVG map configuration and correction wizard."""

from __future__ import annotations

import base64
import math
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
from shapely.ops import nearest_points

from diplomacy_app.domain.models import MapDraft, SvgElementRole, UnitType
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
        self._territory_geometries = territory_geometries(
            draft.svg, (territory.svg_element_id for territory in draft.territories)
        )
        self._row_by_element: dict[str, int] = {}
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Classify the SVG, edit the authored map definition, and place its anchors. "
            "Validation must pass before the reusable map can be saved."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
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
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(
            lambda: self.tabs.setCurrentIndex(self.tabs.currentIndex() - 1)
        )
        buttons.addWidget(self.back_button)
        self.next_button = QPushButton("Next")
        self.next_button.setProperty("primary", True)
        self.next_button.clicked.connect(self._advance)
        buttons.addWidget(self.next_button)
        layout.addLayout(buttons)
        self.yaml_editor.setPlainText(draft.map_yaml)
        self._populate_roles()
        self._reload_anchor_scene()
        self.tabs.currentChanged.connect(self._step_changed)
        self._step_changed(0)
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
        map_layout.addWidget(self.regions_zoom, 0, Qt.AlignmentFlag.AlignRight)
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
        self.tabs.addTab(page, "1  SVG regions")

    def _build_yaml_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel(
            "Edit the durable map.yaml on the left. The validated topology on the right uses "
            "green for army, blue for fleet and purple for shared connections; arrowheads mark "
            "one-way links."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        legend = QLabel(
            '<span style="color:#36734b; font-weight:700">━━ Army</span>&nbsp;&nbsp; '
            '<span style="color:#286b99; font-weight:700">━━ Fleet</span>&nbsp;&nbsp; '
            '<span style="color:#76509a; font-weight:700">━━ Both</span>&nbsp;&nbsp; '
            "→ one-way &nbsp;&nbsp; - - exceptional/off-map"
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
        topology_layout.addWidget(self.topology_zoom, 0, Qt.AlignmentFlag.AlignRight)
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
        self.tabs.addTab(page, "2  Topology")

    def _build_anchor_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(
            "Combine the layers below to find and remove overlaps. Drag any displayed label, "
            "unit or supply-centre star to update only its presentation anchor."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
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
        footer = QHBoxLayout()
        refresh = QPushButton("Reload anchors from YAML")
        refresh.clicked.connect(self._refresh_from_yaml_and_anchors)
        footer.addWidget(refresh)
        footer.addStretch()
        self.placement_zoom = MapZoomControls(self.anchor_canvas)
        footer.addWidget(self.placement_zoom)
        layout.addLayout(footer)
        self.tabs.addTab(page, "3  Placement")

    def _build_assets_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel(
                "The effective symbols are shown at their real map scale on a sample territory. "
                "Defaults are used when custom files are omitted."
            )
        )
        previews = QHBoxLayout()
        army_column = QVBoxLayout()
        self.army_preview_label = QLabel()
        army_column.addWidget(self.army_preview_label)
        self.army_asset_preview = MapCanvas()
        army_column.addWidget(self.army_asset_preview)
        self.army_asset_zoom = MapZoomControls(self.army_asset_preview)
        army_column.addWidget(self.army_asset_zoom)
        fleet_column = QVBoxLayout()
        self.fleet_preview_label = QLabel()
        fleet_column.addWidget(self.fleet_preview_label)
        self.fleet_asset_preview = MapCanvas()
        fleet_column.addWidget(self.fleet_asset_preview)
        self.fleet_asset_zoom = MapZoomControls(self.fleet_asset_preview)
        fleet_column.addWidget(self.fleet_asset_zoom)
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
        self.tabs.addTab(page, "4  Unit symbols")
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
            self.roles.setItem(row, 0, QTableWidgetItem(territory_names.get(element_id, "—")))
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

    def _highlight_row(self, row: int) -> None:
        element_item = self.roles.item(row, 1) if row >= 0 else None
        if element_item is None:
            return
        element_id = element_item.text()
        self.preview.highlight_element(element_id)
        territory = next(
            (item for item in self.draft.territories if item.svg_element_id == element_id), None
        )
        self.hovered_territory.setText(
            f"{territory.name} ({territory.abbreviation}) — {element_id}"
            if territory
            else f"Unconfigured SVG element — {element_id}"
        )

    def _map_hovered(self, x: float, y: float) -> None:
        point = GeometryPoint(x, y)
        for territory in self.draft.territories:
            geometry = self._territory_geometries.get(territory.svg_element_id)
            if geometry is not None and geometry.covers(point):
                row = self._row_by_element.get(territory.svg_element_id)
                if row is not None:
                    self.roles.selectRow(row)
                    territory_item = self.roles.item(row, 0)
                    if territory_item is not None:
                        self.roles.scrollToItem(territory_item)
                self._highlight_row(row if row is not None else -1)
                return
        self.hovered_territory.setText("No playable territory under the pointer.")
        self.preview.highlight_element(None)

    def _role_changed(self, element_id: str, role: SvgElementRole) -> None:
        try:
            self._commit_editor()
            self.draft = self.service.update_map_element_role(self.draft, element_id, role)
            self.yaml_editor.setPlainText(self.draft.map_yaml)
            self._territory_geometries = territory_geometries(
                self.draft.svg,
                (territory.svg_element_id for territory in self.draft.territories),
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

        defs = ElementTree.SubElement(root, tag("defs"))
        colours = {"army": "#36734b", "fleet": "#286b99", "both": "#76509a"}
        for name, colour in colours.items():
            marker = ElementTree.SubElement(
                defs,
                tag("marker"),
                {
                    "id": f"topology-arrow-{name}",
                    "viewBox": "0 0 10 10",
                    "refX": "8",
                    "refY": "5",
                    "markerWidth": "5",
                    "markerHeight": "5",
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
        geometry_by_id = {
            str(item.id): self._territory_geometries.get(item.svg_element_id)
            for item in definition.territories
        }
        layer = ElementTree.SubElement(root, tag("g"), {"id": "topology-preview"})
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
                origin_anchor = definition.presentation.label_anchors[by_id[origin].id]
                destination_anchor = definition.presentation.label_anchors[by_id[destination].id]
                dx = destination_anchor.x - origin_anchor.x
                dy = destination_anchor.y - origin_anchor.y
                distance = max(math.hypot(dx, dy), 1)
                ux, uy = dx / distance, dy / distance
                origin_geometry = geometry_by_id[origin]
                destination_geometry = geometry_by_id[destination]
                if origin_geometry is not None and destination_geometry is not None:
                    left_boundary, right_boundary = nearest_points(
                        origin_geometry.boundary, destination_geometry.boundary
                    )
                    gap = left_boundary.distance(right_boundary)
                    if gap <= 3:
                        midpoint_x = (left_boundary.x + right_boundary.x) / 2
                        midpoint_y = (left_boundary.y + right_boundary.y) / 2
                        half_length = 5
                        start_x = midpoint_x - ux * half_length
                        start_y = midpoint_y - uy * half_length
                        end_x = midpoint_x + ux * half_length
                        end_y = midpoint_y + uy * half_length
                    else:
                        start_x, start_y = left_boundary.x, left_boundary.y
                        end_x, end_y = right_boundary.x, right_boundary.y
                else:
                    midpoint_x = (origin_anchor.x + destination_anchor.x) / 2
                    midpoint_y = (origin_anchor.y + destination_anchor.y) / 2
                    start_x = midpoint_x - ux * 5
                    start_y = midpoint_y - uy * 5
                    end_x = midpoint_x + ux * 5
                    end_y = midpoint_y + uy * 5
                attributes = {
                    "x1": str(start_x),
                    "y1": str(start_y),
                    "x2": str(end_x),
                    "y2": str(end_y),
                    "stroke": colours[kind],
                    "stroke-width": "2",
                    "stroke-opacity": "0.9",
                }
                if origin_geometry is not None and destination_geometry is not None and gap > 3:
                    attributes["stroke-dasharray"] = "3 2"
                if directed:
                    attributes["marker-end"] = f"url(#topology-arrow-{kind})"
                ElementTree.SubElement(layer, tag("line"), attributes)
        return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)

    def _refresh_from_yaml_and_anchors(self) -> None:
        if self._validate():
            self._reload_anchor_scene()

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
                colour,
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

    def _step_changed(self, index: int) -> None:
        self.back_button.setEnabled(index > 0)
        self.next_button.setText(
            "Save configured map" if index == self.tabs.count() - 1 else "Next"
        )
        if index == 1:
            self._validate()

    def _advance(self) -> None:
        index = self.tabs.currentIndex()
        if index == 1 and not self._validate():
            return
        if index < self.tabs.count() - 1:
            self.tabs.setCurrentIndex(index + 1)
        else:
            self._save()

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
