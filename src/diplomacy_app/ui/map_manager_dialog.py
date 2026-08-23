"""Entry point for importing and editing reusable configured maps."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from diplomacy_app.ui.map_wizard import MapWizard


class MapManagerDialog(QDialog):
    def __init__(self, service, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Configure reusable maps")
        self.resize(620, 190)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Import a structured SVG or reopen a configured map. Saving affects future games "
            "only; existing games retain their private map snapshots."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.map_selector = QComboBox()
        row.addWidget(self.map_selector, 1)
        edit = QPushButton("Edit selected map…")
        edit.clicked.connect(self._edit)
        row.addWidget(edit)
        import_map = QPushButton("Import SVG…")
        import_map.clicked.connect(self._import)
        row.addWidget(import_map)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def _refresh(self, select_id=None) -> None:
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
            wizard = MapWizard(self.service, self.service.load_map_draft(map_id), self)
            if wizard.exec() == QDialog.DialogCode.Accepted and wizard.saved_definition is not None:
                self._refresh(wizard.saved_definition.id)
        except Exception as exc:
            QMessageBox.critical(self, "Could not edit map", str(exc))

    def _import(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import structured SVG", "", "SVG files (*.svg)"
        )
        if not filename:
            return
        name, accepted = QInputDialog.getText(
            self,
            "Map name",
            "Name for this reusable map",
            text=Path(filename).stem.replace("-", " ").title(),
        )
        if not accepted or not name.strip():
            return
        try:
            draft = self.service.begin_map_import(name.strip(), Path(filename).read_bytes())
            wizard = MapWizard(self.service, draft, self)
            if wizard.exec() == QDialog.DialogCode.Accepted and wizard.saved_definition is not None:
                self._refresh(wizard.saved_definition.id)
        except Exception as exc:
            QMessageBox.critical(self, "Could not import SVG", str(exc))
