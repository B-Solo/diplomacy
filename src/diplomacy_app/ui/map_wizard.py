"""Tabbed custom SVG map configuration editor."""

from __future__ import annotations

import math
import re
from dataclasses import replace
from typing import Any
from xml.etree import ElementTree

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from diplomacy_app.domain.models import (
    CoastId,
    Location,
    MapDefinition,
    MapDraft,
    MapId,
    Point,
    UnitType,
)
from diplomacy_app.presentation import (
    coast_label_text,
    darken_colour,
    embedded_unit_svg,
)
from diplomacy_app.ui.editor_widgets import DisplayNameEdit, YamlFindBar
from diplomacy_app.ui.map_canvas import (
    MapCanvas,
    MapZoomControls,
    SupplyCentreAnchorItem,
    TextAnchorItem,
    UnitAnchorItem,
)
from diplomacy_app.ui.map_setup_page import MapSetupPage
from diplomacy_app.ui.map_topology import build_topology_diagram

_TERRITORY_FIELD_HEIGHT = 34


class MapWizard(QWidget):
    cancelled = Signal()
    saved = Signal(object)
    promoted = Signal(object)

    def __init__(self, service, draft: MapDraft, parent=None, *, game_map: bool = False) -> None:
        super().__init__(parent)
        self.service = service
        self.draft = draft
        self.game_map = game_map
        self.original_map_id = draft.map_id
        self.saved_definition = None
        self._topology_nodes: dict[str, Point] = {}
        self._topology_node_territories: dict[str, str] = {}
        self._topology_names: dict[str, str] = {}
        self._topology_hovered_territory: str | None = None
        self._selected_territory_label = None
        self._selected_coast_label: Location | None = None
        self._coast_label_items: dict[Location, TextAnchorItem] = {}
        self._unit_preview_items: dict[UnitType, list[UnitAnchorItem]] = {
            UnitType.ARMY: [],
            UnitType.FLEET: [],
        }
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(3)
        self.outer_layout = layout
        if game_map:
            scope = QLabel(
                "This is the map snapshot used by every phase of this game. Saving changes "
                "may invalidate existing orders; review and correct them manually afterward."
            )
            scope.setWordWrap(True)
            scope.setProperty("muted", True)
            layout.addWidget(scope)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
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
        if game_map:
            update_reusable = QPushButton("Update reusable map…")
            update_reusable.clicked.connect(self._update_reusable_map)
            buttons.addWidget(update_reusable)
            save_as_reusable = QPushButton("Save as new reusable map…")
            save_as_reusable.clicked.connect(self._save_as_reusable_map)
            buttons.addWidget(save_as_reusable)
        self.save_button = QPushButton("Save game map" if game_map else "Save configured map")
        self.save_button.setProperty("primary", True)
        self.save_button.clicked.connect(self._save)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self._reload_anchor_scene(fit=True)
        self.yaml_editor.setPlainText(draft.map_yaml)
        self.tabs.currentChanged.connect(self._tab_changed)
        self._validate()
        self._focus_topology_section()

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
        self.tabs.addTab(page, "Definition")

    def _build_setup_tab(self) -> None:
        self.setup_page = MapSetupPage(self.service, self.draft)
        self.setup_page.draft_changed.connect(self._setup_changed)
        self.setup_page.error.connect(self._show_error)
        self.tabs.addTab(self.setup_page, "Powers & start")

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

        self.territory_group = QGroupBox("Selected territory")
        territory_layout = QHBoxLayout(self.territory_group)
        territory_layout.setContentsMargins(10, 8, 10, 8)
        territory_layout.setSpacing(6)
        self.territory_selector = QComboBox()
        self.territory_selector.setMinimumWidth(170)
        for territory in self.draft.territories:
            self.territory_selector.addItem(territory.name, territory.id)
        self.territory_selector.setCurrentIndex(-1)
        self.territory_selector.currentIndexChanged.connect(self._territory_selected)
        self.territory_selector.setFixedHeight(_TERRITORY_FIELD_HEIGHT)
        selector_layout = QVBoxLayout()
        selector_layout.setSpacing(2)
        selector_label = QLabel("Territory")
        selector_label.setBuddy(self.territory_selector)
        selector_layout.addWidget(selector_label)
        selector_layout.addWidget(self.territory_selector)
        territory_layout.addLayout(selector_layout, 2)
        self.canonical_name_editor = QLineEdit()
        self.canonical_name_editor.setMinimumWidth(150)
        self.canonical_name_editor.setFixedHeight(_TERRITORY_FIELD_HEIGHT)
        canonical_layout = QVBoxLayout()
        canonical_layout.setSpacing(2)
        canonical_label = QLabel("Canonical name")
        canonical_label.setBuddy(self.canonical_name_editor)
        canonical_layout.addWidget(canonical_label)
        canonical_layout.addWidget(self.canonical_name_editor)
        territory_layout.addLayout(canonical_layout, 2)
        self.abbreviation_editor = QLineEdit()
        self.abbreviation_editor.setPlaceholderText("ABC")
        self.abbreviation_editor.setMaxLength(3)
        self.abbreviation_editor.setMinimumWidth(95)
        self.abbreviation_editor.setFixedHeight(_TERRITORY_FIELD_HEIGHT)
        abbreviation_layout = QVBoxLayout()
        abbreviation_layout.setSpacing(2)
        abbreviation_label = QLabel("Abbreviation")
        abbreviation_label.setBuddy(self.abbreviation_editor)
        abbreviation_layout.addWidget(abbreviation_label)
        abbreviation_layout.addWidget(self.abbreviation_editor)
        territory_layout.addLayout(abbreviation_layout)
        self.display_name_editor = DisplayNameEdit()
        self.display_name_editor.setToolTip(
            "Press Enter to apply; press Shift+Enter to insert a line break."
        )
        self.display_name_editor.setFixedHeight(_TERRITORY_FIELD_HEIGHT)
        self.display_name_editor.setMinimumWidth(190)
        self.display_name_editor.apply_requested.connect(self._apply_territory_details)
        display_layout = QVBoxLayout()
        display_layout.setSpacing(2)
        display_label = QLabel("Map display name")
        display_label.setBuddy(self.display_name_editor)
        display_layout.addWidget(display_label)
        display_layout.addWidget(self.display_name_editor)
        territory_layout.addLayout(display_layout, 3)
        apply_territory = QPushButton("Apply")
        apply_territory.clicked.connect(self._apply_territory_details)
        territory_layout.addWidget(apply_territory, 0, Qt.AlignmentFlag.AlignBottom)
        self.territory_group.setEnabled(False)
        editing_row.addWidget(self.territory_group, 1)

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
        canvas_row = QHBoxLayout()
        canvas_row.setSpacing(8)
        canvas_row.addWidget(self.anchor_canvas, 1)
        self.hold_underlines_group = QGroupBox("Hold underlines")
        hold_layout = QVBoxLayout(self.hold_underlines_group)
        hold_layout.setContentsMargins(8, 8, 8, 8)
        hold_layout.setSpacing(6)
        explanation = QLabel("Offset from the unit centre")
        explanation.setWordWrap(True)
        explanation.setProperty("muted", True)
        hold_layout.addWidget(explanation)
        (
            self.army_hold_group,
            self.army_hold_x,
            self.army_hold_y,
        ) = self._hold_offset_controls("Armies", self.draft.presentation.army_hold_offset)
        (
            self.fleet_hold_group,
            self.fleet_hold_x,
            self.fleet_hold_y,
        ) = self._hold_offset_controls("Fleets", self.draft.presentation.fleet_hold_offset)
        hold_layout.addWidget(self.army_hold_group)
        hold_layout.addWidget(self.fleet_hold_group)
        hold_layout.addStretch()
        self.hold_underlines_group.setFixedWidth(210)
        canvas_row.addWidget(self.hold_underlines_group)
        layout.addLayout(canvas_row, 1)
        self.placement_zoom = MapZoomControls(self.anchor_canvas)
        self.tabs.addTab(page, "Placement")

    def _hold_offset_controls(
        self, title: str, offset: Point
    ) -> tuple[QGroupBox, QDoubleSpinBox, QDoubleSpinBox]:
        """Build one compact pair of live hold-underline offset controls.

        :param title: Unit category shown on the sub-panel.
        :param offset: Initial relative underline position.
        :return: Sub-panel and its horizontal and vertical controls.
        """
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(4)
        controls = []
        for label_text, value in (("Horizontal", offset.x), ("Vertical", offset.y)):
            row = QHBoxLayout()
            label = QLabel(label_text)
            spin = QDoubleSpinBox()
            spin.setRange(-50, 50)
            spin.setDecimals(1)
            spin.setSingleStep(1)
            spin.setSuffix(" units")
            spin.setValue(value)
            label.setBuddy(spin)
            row.addWidget(label)
            row.addWidget(spin, 1)
            layout.addLayout(row)
            controls.append(spin)
        horizontal, vertical = controls
        horizontal.valueChanged.connect(self._hold_offsets_changed)
        vertical.valueChanged.connect(self._hold_offsets_changed)
        return group, horizontal, vertical

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
            if self.game_map and self.draft.map_id != self.original_map_id:
                self.validation_label.setText("A game's private map ID cannot be changed")
                self.validation_label.setStyleSheet("color: #8a302b")
                return False
            definition = self.service.preview_map_definition(self.draft)
            self.topology_canvas.set_svg(self._topology_svg(definition), fit=True)
            self.validation_label.setText(
                f"Valid: {len(definition.territories)} territories, "
                f"{len(definition.adjacencies)} directed unit connections"
            )
            self.validation_label.setStyleSheet("color: #2f6843")
            self.yaml_editor.document().setModified(False)
            self.setup_page.set_draft(self.draft, repopulate=not self.setup_page.is_dirty)
            self.setup_page.reload_preview()
            return True
        except Exception as exc:
            self.validation_label.setText(str(exc))
            self.validation_label.setStyleSheet("color: #8a302b")
            return False

    def _topology_svg(self, definition) -> bytes:
        diagram = build_topology_diagram(self._preview_svg_without(), definition)
        self._topology_nodes = dict(diagram.node_points)
        self._topology_node_territories = dict(diagram.node_territories)
        self._topology_names = dict(diagram.node_names)
        self._topology_hovered_territory = None
        return diagram.svg

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

    def _reload_anchor_scene(self, *, fit: bool = False) -> None:
        """Rebuild the placement scene from the current compiled draft.

        :param fit: Whether to reset the viewport to show the complete map.
        """
        map_definition = self.service.preview_map_definition(self.draft)
        self.anchor_canvas.set_svg(
            self._preview_svg_without(
                "territory-labels",
                "coast-labels",
                "supply-centres",
                "units",
                "orders",
            ),
            fit=fit,
        )
        self._unit_preview_items = {UnitType.ARMY: [], UnitType.FLEET: []}
        self._selected_coast_label = None
        self._coast_label_items.clear()
        self.coast_rotation.setEnabled(False)
        presentation = map_definition.presentation
        for control, value in (
            (self.army_hold_x, presentation.army_hold_offset.x),
            (self.army_hold_y, presentation.army_hold_offset.y),
            (self.fleet_hold_x, presentation.fleet_hold_offset.x),
            (self.fleet_hold_y, presentation.fleet_hold_offset.y),
        ):
            control.blockSignals(True)
            control.setValue(value)
            control.blockSignals(False)
        territories = {territory.id: territory for territory in map_definition.territories}
        label_mode = self.placement_labels.currentData()
        if self._selected_territory_label is not None:
            self._show_territory_details(territories[self._selected_territory_label])
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
                    presentation.label_colour,
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
                        lambda territory=territory: self._select_territory_label(territory)
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
                    presentation.label_colour,
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
            powers = {power.id: power for power in map_definition.powers}
            owners = map_definition.default_starting_setup.state.supply_centre_owners
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
                centre_item.setToolTip(
                    f"Home territory: {territories[territory].name} — supply centre"
                )
                self.anchor_canvas.scene().addItem(centre_item)
        if self.armies_preview.isChecked():
            unit_entries: list[tuple[Any, str, str | None, Any]] = [
                (territory, "army", None, point)
                for territory, point in presentation.army_anchors.items()
            ]
            self._add_unit_previews(
                unit_entries,
                map_definition.assets.army_svg,
                UnitType.ARMY,
                "#3f7b53",
                map_definition,
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
            asset = map_definition.assets.fleet_svg
            colour = "#356f95"
            self._add_unit_previews(unit_entries, asset, UnitType.FLEET, colour, map_definition)

    def _add_unit_previews(
        self,
        unit_entries,
        asset: bytes,
        unit_type: UnitType,
        fallback_colour: str,
        definition: MapDefinition,
    ) -> None:
        state = definition.default_starting_setup.state
        powers = {power.id: power for power in definition.powers}
        territories = {territory.id: territory for territory in definition.territories}
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
                hold_offset=(
                    definition.presentation.army_hold_offset
                    if unit_type is UnitType.ARMY
                    else definition.presentation.fleet_hold_offset
                ),
            )
            if (unit_type, location) not in starting_units:
                unit_item.setOpacity(0.68)
            tooltip = f"Home territory: {territories[territory].name} — {unit_type.value}"
            if location.coast_id is not None:
                tooltip += f", {coast_label_text(location.coast_id)}"
            unit_item.setToolTip(tooltip)
            self.anchor_canvas.scene().addItem(unit_item)
            self._unit_preview_items[unit_type].append(unit_item)

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
            self.yaml_editor.setPlainText(self.draft.map_yaml)
            self.setup_page.set_draft(self.draft)
            self.setup_page.reload_preview(fit=False)
            self._reload_anchor_scene()
        except Exception as exc:
            self._show_error(f"Could not change label sizes: {exc}")

    def _hold_offsets_changed(self, value: float) -> None:
        """Apply both live underline offsets and persist them in the draft.

        :param value: Newly selected spin-box value; both controls are read together.
        """
        del value
        army_offset = Point(self.army_hold_x.value(), self.army_hold_y.value())
        fleet_offset = Point(self.fleet_hold_x.value(), self.fleet_hold_y.value())
        for unit_type, offset in (
            (UnitType.ARMY, army_offset),
            (UnitType.FLEET, fleet_offset),
        ):
            for item in self._unit_preview_items[unit_type]:
                item.set_hold_offset(offset)
        try:
            self.draft = self.service.update_map_hold_offsets(self.draft, army_offset, fleet_offset)
            self.yaml_editor.setPlainText(self.draft.map_yaml)
            self.setup_page.set_draft(self.draft)
        except Exception as exc:
            self._show_error(f"Could not change hold underlines: {exc}")

    def _select_territory_label(self, territory_id) -> None:
        territory = next(item for item in self.draft.territories if item.id == territory_id)
        self._selected_territory_label = territory_id
        self._show_territory_details(territory)

    def _territory_selected(self, index: int) -> None:
        """Select the territory represented by a combo-box row.

        :param index: Selected combo-box row, or a negative value for no selection.
        """
        if index < 0:
            return
        territory_id = self.territory_selector.itemData(index)
        self._select_territory_label(territory_id)

    def _show_territory_details(self, territory) -> None:
        """Populate the naming controls for one territory.

        :param territory: Territory definition selected on the map or in the selector.
        """
        self._selected_territory_label = territory.id
        self.territory_selector.blockSignals(True)
        self.territory_selector.setCurrentIndex(self.territory_selector.findData(territory.id))
        self.territory_selector.blockSignals(False)
        self.canonical_name_editor.setText(territory.name)
        self.abbreviation_editor.setText(territory.abbreviation)
        self.display_name_editor.setPlainText(territory.display_name)
        self.territory_group.setEnabled(True)

    def _apply_territory_details(self) -> None:
        """Validate and apply the selected territory's user-facing names."""
        territory_id = self._selected_territory_label
        if territory_id is None:
            return
        try:
            self.draft = self.service.update_map_territory_details(
                self.draft,
                territory_id,
                self.canonical_name_editor.text(),
                self.display_name_editor.toPlainText(),
                self.abbreviation_editor.text(),
            )
            self.yaml_editor.setPlainText(self.draft.map_yaml)
            territory = next(item for item in self.draft.territories if item.id == territory_id)
            index = self.territory_selector.findData(territory_id)
            self.territory_selector.setItemText(index, territory.name)
            self.setup_page.set_draft(self.draft)
            self.setup_page.reload_preview(fit=False)
            self._reload_anchor_scene()
        except Exception as exc:
            self._show_error(f"Could not change territory: {exc}")

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
        self.territory_selector.blockSignals(True)
        self.territory_selector.setCurrentIndex(-1)
        self.territory_selector.blockSignals(False)
        self.canonical_name_editor.clear()
        self.abbreviation_editor.clear()
        self.display_name_editor.clear()
        self.territory_group.setEnabled(False)

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
            self.setup_page.set_draft(self.draft)
            self.setup_page.reload_preview(fit=False)
            item = self._coast_label_items.get(location)
            if item is not None:
                item.setRotation(rotation)
        except Exception as exc:
            self._show_error(f"Could not rotate coast label: {exc}")

    def _anchor_moved(self, territory, anchor, coast, point) -> None:
        try:
            self.draft = self.service.update_map_anchor(self.draft, territory, anchor, point, coast)
            self.yaml_editor.setPlainText(self.draft.map_yaml)
            self.setup_page.set_draft(self.draft)
            self.setup_page.reload_preview(fit=False)
        except Exception as exc:
            self._show_error(f"Could not move anchor: {exc}")

    def _focus_topology_section(self) -> None:
        cursor = self.yaml_editor.document().find("territories:")
        if not cursor.isNull():
            self.yaml_editor.setTextCursor(cursor)
            self.yaml_editor.ensureCursorVisible()

    def _setup_changed(self, draft: MapDraft) -> None:
        """Adopt a structured setup edit and refresh the other two pages.

        :param draft: Validated draft emitted by the structured setup page.
        """
        self.draft = draft
        self.yaml_editor.setPlainText(draft.map_yaml)
        self._reload_anchor_scene()

    def _tab_changed(self, index: int) -> None:
        """Commit the page being left and refresh the page being entered.

        :param index: Newly selected tab index.
        """
        if index != 1 and self.setup_page.is_dirty and not self.setup_page.apply_changes():
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(1)
            self.tabs.blockSignals(False)
            return
        if self.yaml_editor.document().isModified() and not self._validate():
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(0)
            self.tabs.blockSignals(False)
            return
        if index == 0:
            self._validate()
        elif index == 1:
            self.setup_page.set_draft(self.draft, repopulate=not self.setup_page.is_dirty)
            self.setup_page.reload_preview()
        elif index == 2:
            self._reload_anchor_scene(fit=True)

    def _show_error(self, text: str) -> None:
        self.message.setText(text)
        self.message.setStyleSheet("color: #8a302b")
        self.message.setVisible(True)

    def _ready_to_save(self) -> bool:
        """Apply structured edits and validate the complete current draft."""
        if self.setup_page.is_dirty and not self.setup_page.apply_changes():
            self.tabs.setCurrentIndex(1)
            return False
        if not self._validate():
            self.tabs.setCurrentIndex(0)
            return False
        return True

    def _save(self) -> None:
        if not self._ready_to_save():
            return
        if self.game_map:
            answer = QMessageBox.warning(
                self,
                "Save edited game map?",
                "This changes the map used by every phase of the game. Existing orders will be "
                "reparsed and revalidated, and may require manual correction.",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Save:
                return
            try:
                self.saved_definition = self.service.save_game_map_draft(self.draft)
                self.saved.emit(self.saved_definition)
            except Exception as exc:
                self._show_error(f"Could not save game map: {exc}")
            return
        try:
            self.saved_definition = self.service.save_map_draft(self.draft)
            self.saved.emit(self.saved_definition)
        except Exception as exc:
            self._show_error(f"Could not save map: {exc}")

    def _update_reusable_map(self) -> None:
        """Replace this game's source reusable map after explicit confirmation."""
        if not self._ready_to_save():
            return
        answer = QMessageBox.warning(
            self,
            "Update reusable map?",
            f'This replaces the canonical reusable map "{self.draft.name}". Its existing '
            "starting setup will be retained.",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Save:
            return
        try:
            definition = self.service.promote_game_map(
                self.draft,
                self.original_map_id,
                self.draft.name,
            )
            self.promoted.emit(definition)
            self.message.setText(f"Updated reusable map {definition.name}")
            self.message.setStyleSheet("color: #2f6843")
            self.message.setVisible(True)
        except Exception as exc:
            self._show_error(f"Could not update reusable map: {exc}")

    def _save_as_reusable_map(self) -> None:
        """Copy this private map to a newly identified reusable map."""
        if not self._ready_to_save():
            return
        name, accepted = QInputDialog.getText(
            self,
            "New reusable map",
            "Map name",
            text=f"{self.draft.name} Copy",
        )
        if not accepted or not name.strip():
            return
        suggested_id = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
        map_id, accepted = QInputDialog.getText(
            self,
            "New reusable map",
            "Stable map ID",
            text=suggested_id,
        )
        if not accepted:
            return
        try:
            definition = self.service.promote_game_map(
                self.draft,
                MapId(map_id.strip()),
                name.strip(),
            )
            self.promoted.emit(definition)
            self.message.setText(f"Saved new reusable map {definition.name}")
            self.message.setStyleSheet("color: #2f6843")
            self.message.setVisible(True)
        except Exception as exc:
            self._show_error(f"Could not save reusable map: {exc}")
