"""Custom SVG map configuration and correction wizard."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from diplomacy_app.domain.models import MapDraft, SvgElementRole
from diplomacy_app.map_library.defaults import DEFAULT_ARMY_SVG, DEFAULT_FLEET_SVG
from diplomacy_app.ui.map_canvas import AnchorItem, MapCanvas, UnitAnchorItem


class MapWizard(QDialog):
    def __init__(self, service, draft: MapDraft, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.draft = draft
        self.saved_definition = None
        self.setWindowTitle(f"Configure map — {draft.name}")
        self.resize(1120, 780)
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
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.save_button = buttons.addButton(
            "Save configured map", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.save_button.setProperty("primary", True)
        buttons.rejected.connect(self.reject)
        self.save_button.clicked.connect(self._save)
        layout.addWidget(buttons)
        self.yaml_editor.setPlainText(draft.map_yaml)
        self._populate_roles()
        self._reload_anchor_scene()

    def _build_classification_tab(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
        self.preview = MapCanvas()
        self.preview.set_svg(self.draft.svg, fit=True)
        self.roles = QTableWidget(0, 2)
        self.roles.setHorizontalHeaderLabels(["SVG element", "Role"])
        self.roles.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.roles.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        splitter = QSplitter()
        splitter.addWidget(self.preview)
        splitter.addWidget(self.roles)
        splitter.setSizes([720, 330])
        layout.addWidget(splitter)
        self.tabs.addTab(page, "1  SVG regions")

    def _build_yaml_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel(
            "This is the durable map.yaml source. Use connection_overrides for exceptional links "
            "and split_coasts for named fleet coasts."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.yaml_editor = QPlainTextEdit()
        self.yaml_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.topology = QPlainTextEdit()
        self.topology.setReadOnly(True)
        self.topology.setPlaceholderText("Validate to inspect the complete effective topology.")
        splitter.addWidget(self.yaml_editor)
        splitter.addWidget(self.topology)
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
        self.tabs.addTab(page, "2  Definition & topology")

    def _build_anchor_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(
            "Drag markers to place labels, army/fleet symbols, and supply-centre stars. "
            "Gold = label, green = army, blue = fleet, red = supply centre."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("Placement preview"))
        self.armies_preview = QPushButton("Armies")
        self.fleets_preview = QPushButton("Fleets")
        self.armies_preview.setCheckable(True)
        self.fleets_preview.setCheckable(True)
        self.preview_group = QButtonGroup(self)
        self.preview_group.setExclusive(True)
        self.preview_group.addButton(self.armies_preview)
        self.preview_group.addButton(self.fleets_preview)
        self.armies_preview.setChecked(True)
        self.armies_preview.toggled.connect(self._preview_changed)
        self.fleets_preview.toggled.connect(self._preview_changed)
        preview_row.addWidget(self.armies_preview)
        preview_row.addWidget(self.fleets_preview)
        preview_row.addStretch()
        layout.addLayout(preview_row)
        self.anchor_canvas = MapCanvas()
        layout.addWidget(self.anchor_canvas, 1)
        refresh = QPushButton("Reload anchors from YAML")
        refresh.clicked.connect(self._refresh_from_yaml_and_anchors)
        layout.addWidget(refresh)
        self.tabs.addTab(page, "3  Placement")

    def _build_assets_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Optional custom unit symbols. Defaults are used when omitted."))
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
        for element_id, role in sorted(self.draft.element_roles.items()):
            row = self.roles.rowCount()
            self.roles.insertRow(row)
            self.roles.setItem(row, 0, QTableWidgetItem(element_id))
            selector = QComboBox()
            for value in SvgElementRole:
                selector.addItem(value.value.replace("_", " ").title(), value)
            selector.setCurrentIndex(selector.findData(role))
            selector.currentIndexChanged.connect(
                lambda _index, element_id=element_id, selector=selector: self._role_changed(
                    element_id, selector.currentData()
                )
            )
            self.roles.setCellWidget(row, 1, selector)

    def _role_changed(self, element_id: str, role: SvgElementRole) -> None:
        try:
            self._commit_editor()
            self.draft = self.service.update_map_element_role(self.draft, element_id, role)
            self.yaml_editor.setPlainText(self.draft.map_yaml)
            self._reload_anchor_scene()
        except Exception as exc:
            QMessageBox.critical(self, "Could not change region role", str(exc))

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
            self.topology.clear()
            return False
        try:
            self.draft = self.service.refresh_map_draft(self.draft)
            definition = self.service.preview_map_definition(self.draft)
            topology = [
                f"{edge.unit_type.value:5}  {edge.origin.territory_id}"
                + (f"/{edge.origin.coast_id}" if edge.origin.coast_id else "")
                + "  →  "
                + str(edge.destination.territory_id)
                + (f"/{edge.destination.coast_id}" if edge.destination.coast_id else "")
                for edge in sorted(
                    definition.adjacencies,
                    key=lambda item: (
                        item.unit_type.value,
                        item.origin.territory_id,
                        item.origin.coast_id or "",
                        item.destination.territory_id,
                        item.destination.coast_id or "",
                    ),
                )
            ]
            self.topology.setPlainText("\n".join(topology))
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

    def _refresh_from_yaml_and_anchors(self) -> None:
        if self._validate():
            self._reload_anchor_scene()

    def _reload_anchor_scene(self) -> None:
        self.anchor_canvas.set_svg(self.draft.svg, fit=True)
        presentation = self.draft.presentation
        entries: list[tuple[Any, str, str | None, Any, str]] = []
        entries.extend(
            (territory, "label", None, point, "#c58d24")
            for territory, point in presentation.label_anchors.items()
        )
        entries.extend(
            (territory, "supply_centre", None, point, "#9d3e38")
            for territory, point in presentation.supply_centre_anchors.items()
        )
        for territory, anchor, coast, point, colour in entries:
            item = AnchorItem(
                point,
                colour,
                lambda new_point, territory=territory, anchor=anchor, coast=coast: (
                    self._anchor_moved(territory, anchor, coast, new_point)
                ),
            )
            item.setToolTip(f"{territory}: {anchor}" + (f" ({coast})" if coast else ""))
            self.anchor_canvas.scene().addItem(item)
        if self.armies_preview.isChecked():
            unit_entries: list[tuple[Any, str, str | None, Any]] = [
                (territory, "army", None, point)
                for territory, point in presentation.army_anchors.items()
            ]
            asset = self.draft.army_svg or DEFAULT_ARMY_SVG
            colour = "#3f7b53"
        else:
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
        if checked:
            self._reload_anchor_scene()

    def _anchor_moved(self, territory, anchor, coast, point) -> None:
        try:
            self.draft = self.service.update_map_anchor(self.draft, territory, anchor, point, coast)
            self.yaml_editor.setPlainText(self.draft.map_yaml)
        except Exception as exc:
            QMessageBox.critical(self, "Could not move anchor", str(exc))

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

    def _save(self) -> None:
        if not self._validate():
            self.tabs.setCurrentIndex(1)
            return
        try:
            self.saved_definition = self.service.save_map_draft(self.draft)
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Could not save map", str(exc))
