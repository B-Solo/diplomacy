"""Configured-map selection, import, and game-specific starting setup."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import yaml
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from diplomacy_app.domain.models import (
    CoastId,
    DislodgedUnit,
    GameLocation,
    GameSettings,
    GameState,
    Location,
    NewGameRequest,
    PhaseId,
    PowerId,
    Season,
    StartingSetup,
    TerritoryId,
    UnitPosition,
    UnitType,
    VisibilityPolicy,
)


def _location_text(value: Location) -> str:
    return str(value.territory_id) + (f"/{value.coast_id}" if value.coast_id else "")


def _location(value: str) -> Location:
    territory, separator, coast = str(value).partition("/")
    return Location(TerritoryId(territory), CoastId(coast) if separator else None)


def setup_text(setup: StartingSetup) -> str:
    state = setup.state
    value = {
        "year": setup.phase_id.year,
        "season": setup.phase_id.season.value,
        "units": [
            {
                "power": unit.power_id,
                "type": unit.unit_type.value,
                "location": _location_text(unit.location),
            }
            for unit in state.units
        ],
        "dislodged_units": [
            {
                "power": item.unit.power_id,
                "type": item.unit.unit_type.value,
                "location": _location_text(item.unit.location),
                "retreat_options": [_location_text(option) for option in item.retreat_options],
            }
            for item in state.dislodged_units
        ],
        "territory_controllers": {
            str(key): owner for key, owner in state.territory_controllers.items() if owner
        },
        "supply_centre_owners": {
            str(key): owner for key, owner in state.supply_centre_owners.items() if owner
        },
    }
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True)


def parse_setup(text: str) -> StartingSetup:
    value = yaml.safe_load(text)
    if not isinstance(value, dict):
        raise ValueError("Starting setup must be a YAML mapping")
    units = tuple(
        UnitPosition(
            PowerId(str(item["power"])),
            UnitType(str(item["type"])),
            _location(str(item["location"])),
        )
        for item in value.get("units", [])
    )
    dislodged = tuple(
        DislodgedUnit(
            UnitPosition(
                PowerId(str(item["power"])),
                UnitType(str(item["type"])),
                _location(str(item["location"])),
            ),
            tuple(_location(str(option)) for option in item.get("retreat_options", [])),
        )
        for item in value.get("dislodged_units", [])
    )
    controllers = MappingProxyType(
        {
            TerritoryId(str(key)): PowerId(str(owner)) if owner else None
            for key, owner in value.get("territory_controllers", {}).items()
        }
    )
    owners = MappingProxyType(
        {
            TerritoryId(str(key)): PowerId(str(owner)) if owner else None
            for key, owner in value.get("supply_centre_owners", {}).items()
        }
    )
    return StartingSetup(
        PhaseId(int(value.get("year", 1901)), Season(str(value.get("season", "spring")))),
        GameState(units, dislodged, controllers, owners),
    )


class NewGameWorkspace(QWidget):
    cancelled = Signal()
    created = Signal(object)
    edit_requested = Signal(object)

    def __init__(self, service, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.created_session = None
        layout = QVBoxLayout(self)
        title = QLabel("New Diplomacy game")
        title.setStyleSheet("font: 700 22pt Georgia, serif; color: #33483d")
        layout.addWidget(title)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._build_game_tab()
        self._build_setup_tab()
        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.cancelled)
        buttons.addWidget(cancel)
        buttons.addStretch()
        create = QPushButton("Create game")
        create.setProperty("primary", True)
        create.clicked.connect(self._create)
        buttons.addWidget(create)
        layout.addLayout(buttons)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: #8a302b")
        self.message.setVisible(False)
        layout.insertWidget(layout.count() - 1, self.message)
        self._refresh_maps()

    def _build_game_tab(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        map_row = QWidget()
        map_layout = QHBoxLayout(map_row)
        map_layout.setContentsMargins(0, 0, 0, 0)
        self.map_selector = QComboBox()
        self.map_selector.currentIndexChanged.connect(self._map_changed)
        map_layout.addWidget(self.map_selector, 1)
        edit = QPushButton("Edit map…")
        edit.clicked.connect(self._edit_map)
        import_map = QPushButton("Import SVG…")
        import_map.clicked.connect(self._import_map)
        map_layout.addWidget(edit)
        map_layout.addWidget(import_map)
        form.addRow("Configured map", map_row)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Friday night game")
        form.addRow("Game name", self.name)
        folder_row = QWidget()
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        self.folder = QLineEdit()
        choose = QPushButton("Choose…")
        choose.clicked.connect(self._choose_folder)
        folder_layout.addWidget(self.folder, 1)
        folder_layout.addWidget(choose)
        form.addRow("Game folder", folder_row)
        self.fog = QCheckBox("Enable Fog of War")
        form.addRow("Visibility", self.fog)
        self.fog_depth = QSpinBox()
        self.fog_depth.setRange(0, 10)
        self.fog_depth.setValue(1)
        form.addRow("Visibility adjacency depth", self.fog_depth)
        explanation = QCheckBox("Show adjudication outcomes when hovering orders")
        self.explanations = explanation
        form.addRow("Optional explanations", explanation)
        self.tabs.addTab(page, "Game")

    def _build_setup_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(
            "The selected map's starting state is shown below. You may change the year, season, "
            "units, retreat state, ownership, or territorial control for this game only."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        self.setup_editor = QPlainTextEdit()
        self.setup_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.setup_editor, 1)
        self.tabs.addTab(page, "Starting position")

    def _refresh_maps(self, select_id=None) -> None:
        self.map_selector.blockSignals(True)
        self.map_selector.clear()
        for item in self.service.list_maps():
            self.map_selector.addItem(f"{item.name} — {item.power_count} powers", item.map_id)
        if select_id is not None:
            index = self.map_selector.findData(select_id)
            if index >= 0:
                self.map_selector.setCurrentIndex(index)
        self.map_selector.blockSignals(False)
        self._map_changed()

    def _map_changed(self) -> None:
        map_id = self.map_selector.currentData()
        if map_id is None:
            self.setup_editor.clear()
            return
        try:
            draft = self.service.prepare_new_game(map_id)
            self.setup_editor.setPlainText(setup_text(draft.starting_setup))
        except Exception as exc:
            self._show_error(f"Could not load map: {exc}")

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose an empty game folder")
        if folder:
            self.folder.setText(folder)

    def _import_map(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import structured SVG", "", "SVG files (*.svg)"
        )
        if not filename:
            return
        try:
            name = Path(filename).stem.replace("-", " ").title()
            draft = self.service.begin_map_import(name, Path(filename).read_bytes())
            self.edit_requested.emit(draft)
        except Exception as exc:
            self._show_error(f"Could not import SVG: {exc}")

    def _edit_map(self) -> None:
        map_id = self.map_selector.currentData()
        if map_id is None:
            return
        try:
            self.edit_requested.emit(self.service.load_map_draft(map_id))
        except Exception as exc:
            self._show_error(f"Could not edit map: {exc}")

    def map_saved(self, definition) -> None:
        self._refresh_maps(definition.id)

    def _create(self) -> None:
        try:
            if not self.name.text().strip():
                raise ValueError("Enter a game name")
            if not self.folder.text().strip():
                raise ValueError("Choose the self-contained game folder")
            request = NewGameRequest(
                self.name.text().strip(),
                GameLocation(Path(self.folder.text()).expanduser().resolve()),
                self.map_selector.currentData(),
                parse_setup(self.setup_editor.toPlainText()),
                GameSettings(
                    VisibilityPolicy(self.fog.isChecked(), self.fog_depth.value()),
                    self.explanations.isChecked(),
                ),
            )
            self.created_session = self.service.create_game(request)
            self.created.emit(self.created_session)
        except Exception as exc:
            self._show_error(f"Could not create game: {exc}")

    def _show_error(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(True)
