"""Main-window workspace for importing and editing reusable maps."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MapManagerWorkspace(QWidget):
    cancelled = Signal()
    edit_requested = Signal(object)

    def __init__(self, service, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        layout = QVBoxLayout(self)
        title = QLabel("Configure reusable maps")
        title.setStyleSheet("font: 700 22pt Georgia, serif; color: #33483d")
        layout.addWidget(title)
        note = QLabel(
            "Import a structured SVG or reopen a configured map. Saving affects future games "
            "only; existing games retain their private map snapshots."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.map_selector = QComboBox()
        row.addWidget(self.map_selector, 1)
        edit = QPushButton("Edit selected map")
        edit.setProperty("primary", True)
        edit.clicked.connect(self._edit)
        row.addWidget(edit)
        import_map = QPushButton("Import SVG…")
        import_map.clicked.connect(self._import)
        row.addWidget(import_map)
        layout.addLayout(row)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: #8a302b")
        self.message.setVisible(False)
        layout.addWidget(self.message)
        layout.addStretch()
        close = QPushButton("Back")
        close.clicked.connect(self.cancelled)
        layout.addWidget(close)
        self.refresh()

    def refresh(self, select_id=None) -> None:
        self.map_selector.clear()
        for item in self.service.list_maps():
            self.map_selector.addItem(f"{item.name} — {item.power_count} powers", item.map_id)
        if select_id is not None:
            index = self.map_selector.findData(select_id)
            if index >= 0:
                self.map_selector.setCurrentIndex(index)

    def _edit(self) -> None:
        map_id = self.map_selector.currentData()
        if map_id is None:
            return
        try:
            self.edit_requested.emit(self.service.load_map_draft(map_id))
        except Exception as exc:
            self._show_error(f"Could not edit map: {exc}")

    def _import(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import structured SVG", "", "SVG files (*.svg)"
        )
        if not filename:
            return
        try:
            name = Path(filename).stem.replace("-", " ").title()
            self.edit_requested.emit(
                self.service.begin_map_import(name, Path(filename).read_bytes())
            )
        except Exception as exc:
            self._show_error(f"Could not import SVG: {exc}")

    def _show_error(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(True)
