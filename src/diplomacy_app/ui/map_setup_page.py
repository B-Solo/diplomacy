"""Structured power and starting-position editor for configured maps."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from diplomacy_app.domain.models import Location, MapDraft, Season, UnitType
from diplomacy_app.ui.map_canvas import MapCanvas, MapZoomControls
from diplomacy_app.ui.map_setup_model import PowerSetupRow, build_setup

_COLUMNS = (
    "ID",
    "Name",
    "Colour",
    "Home centres",
    "Starting centres",
    "Starting territories",
    "Initial units",
)


class MapSetupPage(QWidget):
    """Edit powers and starting state with an exact gameplay-renderer preview."""

    draft_changed = Signal(object)
    error = Signal(str)

    def __init__(self, service, draft: MapDraft, parent=None) -> None:
        """Create a structured setup editor.

        :param service: Application service used for validated draft mutations and previewing.
        :param draft: Initial authored map draft.
        :param parent: Optional owning Qt widget.
        """
        super().__init__(parent)
        self.service = service
        self.draft = draft
        self._populating = False
        self._dirty = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(6)

        phase_group = QGroupBox("Starting phase")
        phase_layout = QHBoxLayout(phase_group)
        phase_layout.addWidget(QLabel("Year"))
        self.year = QSpinBox()
        self.year.setRange(1, 9999)
        phase_layout.addWidget(self.year)
        phase_layout.addWidget(QLabel("Season"))
        self.season = QComboBox()
        for season in Season:
            label = "Year End" if season is Season.YEAR_END else season.value.title()
            self.season.addItem(label, season)
        phase_layout.addWidget(self.season)
        phase_layout.addStretch()
        editor_layout.addWidget(phase_group)

        powers_group = QGroupBox("Powers and starting position")
        powers_layout = QVBoxLayout(powers_group)
        hint = QLabel(
            "Separate territory IDs with commas. Enter units as “A territory” or "
            "“F territory/coast”, separated by commas."
        )
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        powers_layout.addWidget(hint)
        self.powers = QTableWidget(0, len(_COLUMNS))
        self.powers.setHorizontalHeaderLabels(_COLUMNS)
        self.powers.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.powers.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.powers.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.powers.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.powers.setAlternatingRowColors(True)
        self.powers.itemChanged.connect(self._mark_dirty)
        powers_layout.addWidget(self.powers, 1)
        power_actions = QHBoxLayout()
        add_power = QPushButton("Add power")
        add_power.clicked.connect(self._add_power)
        power_actions.addWidget(add_power)
        remove_power = QPushButton("Remove selected")
        remove_power.clicked.connect(self._remove_power)
        power_actions.addWidget(remove_power)
        choose_colour = QPushButton("Choose selected colour")
        choose_colour.clicked.connect(self._choose_power_colour)
        power_actions.addWidget(choose_colour)
        power_actions.addStretch()
        powers_layout.addLayout(power_actions)
        editor_layout.addWidget(powers_group, 1)

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
        editor_layout.addWidget(self.map_colours_group)

        apply_row = QHBoxLayout()
        self.apply_button = QPushButton("Apply powers and starting position")
        self.apply_button.setProperty("primary", True)
        self.apply_button.clicked.connect(self.apply_changes)
        apply_row.addWidget(self.apply_button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        apply_row.addWidget(self.status, 1)
        editor_layout.addLayout(apply_row)

        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Starting position — exact gameplay rendering")
        title.setProperty("muted", True)
        preview_layout.addWidget(title)
        self.canvas = MapCanvas()
        preview_layout.addWidget(self.canvas, 1)
        self.zoom = MapZoomControls(self.canvas)

        splitter.addWidget(editor)
        splitter.addWidget(preview)
        splitter.setSizes([640, 700])
        layout.addWidget(splitter, 1)
        self.splitter = splitter
        self._populate()
        self.year.valueChanged.connect(self._mark_dirty)
        self.season.currentIndexChanged.connect(self._mark_dirty)
        self.reload_preview()

    @staticmethod
    def _joined(values) -> str:
        """Return comma-separated stable identifiers for one table cell.

        :param values: Iterable of identifier-like values.
        :return: Deterministically ordered comma-separated text.
        """
        return ", ".join(sorted(str(value) for value in values))

    @staticmethod
    def _location_text(location: Location) -> str:
        """Return authored YAML notation for one unit location.

        :param location: Province and optional named coast.
        :return: Stable location text.
        """
        return str(location.territory_id) + (
            f"/{location.coast_id}" if location.coast_id is not None else ""
        )

    def _populate(self) -> None:
        """Populate structured controls from the current immutable draft."""
        self._populating = True
        setup = self.draft.default_starting_setup
        self.year.setValue(setup.phase_id.year)
        self.season.setCurrentIndex(self.season.findData(setup.phase_id.season))
        self.powers.setRowCount(0)
        for power in self.draft.powers:
            row = self.powers.rowCount()
            self.powers.insertRow(row)
            state = setup.state
            cells = (
                str(power.id),
                power.name,
                power.colour,
                self._joined(power.home_supply_centres),
                self._joined(
                    territory
                    for territory, owner in state.supply_centre_owners.items()
                    if owner == power.id
                ),
                self._joined(
                    territory
                    for territory, controller in state.territory_controllers.items()
                    if controller == power.id
                ),
                ", ".join(
                    ("A" if unit.unit_type is UnitType.ARMY else "F")
                    + " "
                    + self._location_text(unit.location)
                    for unit in state.units
                    if unit.power_id == power.id
                ),
            )
            for column, value in enumerate(cells):
                self.powers.setItem(row, column, QTableWidgetItem(value))
            self._style_power_colour(row)
        self._refresh_colour_buttons()
        self._populating = False
        self._dirty = False

    @property
    def is_dirty(self) -> bool:
        """Return whether structured fields contain unapplied changes."""
        return self._dirty

    def _mark_dirty(self, *_args) -> None:
        """Record that a structured field differs from the shared draft."""
        if not self._populating:
            self._dirty = True

    def set_draft(self, draft: MapDraft, *, repopulate: bool = True) -> None:
        """Synchronise this page with a draft changed on another page.

        :param draft: Latest shared map draft.
        :param repopulate: Whether to replace currently edited structured fields.
        """
        self.draft = draft
        if repopulate:
            self._populate()

    def reload_preview(self, *, fit: bool = True) -> bool:
        """Render the current starting position through the gameplay pipeline.

        :param fit: Whether to fit the complete map after replacing the scene.
        :return: Whether rendering succeeded.
        """
        try:
            self.canvas.set_scene(self.service.preview_map_setup(self.draft), fit=fit)
            return True
        except Exception as exc:
            self._set_status(f"Could not render starting position: {exc}", error=True)
            return False

    def _cell_text(self, row: int, column: int) -> str:
        """Return trimmed text from a required table cell.

        :param row: Table row index.
        :param column: Table column index.
        :return: Trimmed cell text, or an empty string for a missing item.
        """
        item = self.powers.item(row, column)
        return item.text().strip() if item is not None else ""

    def apply_changes(self) -> bool:
        """Validate the structured form, update YAML, and refresh the exact preview.

        :return: Whether the complete structured edit was accepted.
        """
        try:
            rows = tuple(
                PowerSetupRow(*(self._cell_text(row, column) for column in range(len(_COLUMNS))))
                for row in range(self.powers.rowCount())
            )
            powers, setup = build_setup(
                self.draft,
                self.year.value(),
                Season(self.season.currentData()),
                rows,
            )
            updated = self.service.update_map_setup(self.draft, powers, setup)
            validation = self.service.validate_map_draft(updated)
            if not validation.is_valid:
                messages = "; ".join(value.issue.message for value in validation.issues)
                raise ValueError(messages)
            self.draft = updated
            self._populate()
            self.reload_preview()
            self._set_status("Powers and starting position applied", error=False)
            self.draft_changed.emit(updated)
            return True
        except Exception as exc:
            self._set_status(str(exc), error=True)
            self.error.emit(str(exc))
            return False

    def _add_power(self) -> None:
        """Append a usable, uniquely identified blank power row."""
        existing = {self._cell_text(row, 0) for row in range(self.powers.rowCount())}
        power_id = "new-power"
        suffix = 2
        while power_id in existing:
            power_id = f"new-power-{suffix}"
            suffix += 1
        row = self.powers.rowCount()
        self.powers.insertRow(row)
        for column, value in enumerate((power_id, "New power", "#777777", "", "", "", "")):
            self.powers.setItem(row, column, QTableWidgetItem(value))
        self._style_power_colour(row)
        self.powers.selectRow(row)
        self._dirty = True

    def _remove_power(self) -> None:
        """Remove the currently selected power row from the pending form."""
        row = self.powers.currentRow()
        if row >= 0:
            self.powers.removeRow(row)
            self._dirty = True

    def _choose_power_colour(self) -> None:
        """Choose the colour of the currently selected pending power."""
        row = self.powers.currentRow()
        if row < 0:
            self._set_status("Select a power row first", error=True)
            return
        current = QColor(self._cell_text(row, 2))
        selected = QColorDialog.getColor(current, self, "Choose power colour")
        if selected.isValid():
            self._set_power_colour(row, selected.name())

    def _set_power_colour(self, row: int, colour: str) -> None:
        """Set and visually preview one power-table colour.

        :param row: Power table row.
        :param colour: Colour in #RRGGBB notation.
        """
        item = self.powers.item(row, 2)
        if item is None:
            item = QTableWidgetItem()
            self.powers.setItem(row, 2, item)
        item.setText(colour.lower())
        self._style_power_colour(row)
        self._dirty = True

    def _style_power_colour(self, row: int) -> None:
        """Apply readable foreground and background to one colour cell.

        :param row: Power table row to style.
        """
        item = self.powers.item(row, 2)
        if item is None:
            return
        colour = QColor(item.text())
        if not colour.isValid():
            return
        item.setBackground(colour)
        item.setForeground(QColor("#171714") if colour.lightness() >= 145 else QColor("#fffdf7"))

    def _refresh_colour_buttons(self) -> None:
        """Synchronise map-colour button labels and contrast with the draft."""
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
        """Open a colour chooser for one map-wide presentation field.

        :param field: MapPresentation colour field to edit.
        """
        current = getattr(self.draft.presentation, field)
        label = field.removesuffix("_colour").replace("_", " ").title()
        selected = QColorDialog.getColor(QColor(current), self, f"Choose {label}")
        if selected.isValid():
            self._set_map_colour(field, selected.name())

    def _set_map_colour(self, field: str, colour: str) -> None:
        """Apply one map-wide colour and refresh the exact preview.

        :param field: MapPresentation colour field to edit.
        :param colour: Colour in #RRGGBB notation.
        """
        values = {
            "label_colour": self.draft.presentation.label_colour,
            "inaccessible_region_colour": self.draft.presentation.inaccessible_region_colour,
            "sea_colour": self.draft.presentation.sea_colour,
            "unclaimed_region_colour": self.draft.presentation.unclaimed_region_colour,
        }
        if field not in values:
            self._set_status(f"Unknown map colour: {field}", error=True)
            return
        values[field] = colour
        try:
            updated = self.service.update_map_colours(
                self.draft,
                values["label_colour"],
                values["inaccessible_region_colour"],
                values["sea_colour"],
                values["unclaimed_region_colour"],
            )
            self.draft = updated
            self._refresh_colour_buttons()
            self.reload_preview(fit=False)
            self.draft_changed.emit(updated)
        except Exception as exc:
            self._set_status(f"Could not change map colour: {exc}", error=True)
            self.error.emit(str(exc))

    def _set_status(self, text: str, *, error: bool) -> None:
        """Show one concise result beside the apply action.

        :param text: User-facing result or error text.
        :param error: Whether to apply error rather than success styling.
        """
        self.status.setText(text)
        self.status.setStyleSheet("color: #8a302b" if error else "color: #2f6843")
