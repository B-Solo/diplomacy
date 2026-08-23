"""Main desktop window and application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from diplomacy_app.application import build_application
from diplomacy_app.domain.models import AdvancedPhase, FinalisationRequired, GameLocation
from diplomacy_app.ui.background_tasks import BackgroundTask
from diplomacy_app.ui.map_manager_dialog import MapManagerDialog
from diplomacy_app.ui.map_workspace import MapWorkspace
from diplomacy_app.ui.new_game_dialog import NewGameDialog
from diplomacy_app.ui.orders_workspace import OrdersWorkspace
from diplomacy_app.ui.style import STYLE


class ApplicationWindow(QMainWindow):
    def __init__(self, service) -> None:
        super().__init__()
        self.service = service
        self.session = None
        self.thread_pool = QThreadPool.globalInstance()
        self.setWindowTitle("Diplomacy Gamemaster")
        self.resize(1280, 840)
        self.setMinimumSize(860, 620)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header())
        self.stack = QStackedWidget()
        self.welcome = self._welcome_page()
        self.map_workspace = MapWorkspace(service)
        self.orders_workspace = OrdersWorkspace()
        self.orders_workspace.save_requested.connect(self._save_orders)
        self.orders_workspace.final_requested.connect(self._set_final)
        self.orders_workspace.resolve_requested.connect(self._resolve)
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.map_workspace)
        self.stack.addWidget(self.orders_workspace)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self._season_bar())
        self.setCentralWidget(root)
        self.statusBar().showMessage("Ready")

    def _header(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #33483d; color: #fffaf0; border: 0; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 8, 12, 8)
        brand = QLabel("⚜  Diplomacy")
        brand.setStyleSheet("font: 700 17pt Georgia, serif; color: #f7edcf")
        layout.addWidget(brand)
        self.game_button = QPushButton("No game open")
        self.game_button.setStyleSheet(
            "color: #fffaf0; background: transparent; border-color: #829487"
        )
        self.game_button.clicked.connect(self._show_game_choices)
        layout.addWidget(self.game_button)
        layout.addStretch()
        self.tabs = QTabBar()
        self.tabs.addTab("Map")
        self.tabs.addTab("Orders")
        self.tabs.currentChanged.connect(self._tab_changed)
        self.tabs.setVisible(False)
        layout.addWidget(self.tabs)
        return frame

    def _welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Set the board")
        title.setStyleSheet("font: 700 28pt Georgia, serif; color: #33483d")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        subtitle = QLabel("Open a self-contained game folder or begin a new campaign.")
        subtitle.setProperty("muted", True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        buttons = QHBoxLayout()
        open_button = QPushButton("Open game folder…")
        open_button.clicked.connect(self._open_game)
        new_button = QPushButton("New game…")
        new_button.setProperty("primary", True)
        new_button.clicked.connect(self._new_game)
        buttons.addWidget(open_button)
        buttons.addWidget(new_button)
        maps_button = QPushButton("Configure maps…")
        maps_button.clicked.connect(self._configure_maps)
        buttons.addWidget(maps_button)
        layout.addLayout(buttons)
        self.recent_layout = QVBoxLayout()
        layout.addLayout(self.recent_layout)
        return page

    def _season_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet("QFrame { background: #f6f1e3; border-top: 1px solid #b7ae97; }")
        layout = QHBoxLayout(bar)
        self.previous = QPushButton("←")
        self.next = QPushButton("→")
        self.phase_selector = QComboBox()
        self.current_label = QLabel("Current")
        self.previous.clicked.connect(lambda: self._step_phase(-1))
        self.next.clicked.connect(lambda: self._step_phase(1))
        self.phase_selector.currentIndexChanged.connect(self._phase_selected)
        layout.addStretch()
        layout.addWidget(self.previous)
        layout.addWidget(self.phase_selector)
        layout.addWidget(self.current_label)
        layout.addWidget(self.next)
        layout.addStretch()
        self.season_bar = bar
        bar.setVisible(False)
        return bar

    def start(self) -> None:
        try:
            self.set_session(self.service.start())
        except Exception as exc:
            QMessageBox.warning(self, "Could not reopen last game", str(exc))
            self.set_session(self.service.start())

    def set_session(self, session, *, open_map: bool = False) -> None:
        self.session = session
        game = session.game
        self.tabs.setVisible(game is not None)
        self.season_bar.setVisible(game is not None)
        if game is None:
            self.stack.setCurrentWidget(self.welcome)
            self.game_button.setText("No game open")
            self._populate_recent(session)
            return
        self.game_button.setText(game.name + "  ▾")
        self.phase_selector.blockSignals(True)
        self.phase_selector.clear()
        for phase in game.phases:
            self.phase_selector.addItem(phase.label, phase)
        self.phase_selector.setCurrentIndex(self.phase_selector.findData(session.phase.phase_id))
        self.phase_selector.blockSignals(False)
        self.current_label.setVisible(session.phase.phase_id == game.current_phase)
        index = self.phase_selector.currentIndex()
        self.previous.setEnabled(index > 0)
        self.next.setEnabled(index < self.phase_selector.count() - 1)
        self.map_workspace.set_session(session)
        self.orders_workspace.set_session(session)
        if open_map:
            self.tabs.setCurrentIndex(0)
        self._tab_changed(self.tabs.currentIndex())

    def _populate_recent(self, session) -> None:
        while self.recent_layout.count():
            item = self.recent_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if session.recent_games:
            heading = QLabel("Recent games")
            heading.setStyleSheet("font-weight: 700; margin-top: 18px")
            self.recent_layout.addWidget(heading)
        for recent in session.recent_games[:6]:
            button = QPushButton(f"{recent.name}  —  {recent.current_phase.label}")
            button.clicked.connect(
                lambda _checked=False, location=recent.location: self._open_location(location)
            )
            self.recent_layout.addWidget(button)

    def _tab_changed(self, index: int) -> None:
        if not self.session or not self.session.game:
            return
        self.stack.setCurrentWidget(self.map_workspace if index == 0 else self.orders_workspace)

    def _show_game_choices(self) -> None:
        message = QMessageBox(self)
        message.setWindowTitle("Game")
        message.setText(
            self.session.game.name if self.session and self.session.game else "Diplomacy"
        )
        open_button = message.addButton("Open game folder…", QMessageBox.ButtonRole.ActionRole)
        new_button = message.addButton("New game…", QMessageBox.ButtonRole.ActionRole)
        maps_button = message.addButton("Configure maps…", QMessageBox.ButtonRole.ActionRole)
        message.addButton(QMessageBox.StandardButton.Cancel)
        message.exec()
        if message.clickedButton() is open_button:
            self._open_game()
        elif message.clickedButton() is new_button:
            self._new_game()
        elif message.clickedButton() is maps_button:
            self._configure_maps()

    def _open_game(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open game folder")
        if folder:
            self._open_location(GameLocation(Path(folder).resolve()))

    def _open_location(self, location) -> None:
        try:
            self.set_session(self.service.open_game(location), open_map=True)
        except Exception as exc:
            QMessageBox.critical(self, "Could not open game", str(exc))

    def _new_game(self) -> None:
        dialog = NewGameDialog(self.service, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.set_session(dialog.created_session, open_map=True)

    def _configure_maps(self) -> None:
        MapManagerDialog(self.service, self).exec()

    def _phase_selected(self) -> None:
        phase = self.phase_selector.currentData()
        if phase is None or not self.session or phase == self.session.phase.phase_id:
            return
        try:
            self.set_session(self.service.select_phase(phase))
        except Exception as exc:
            QMessageBox.critical(self, "Could not open phase", str(exc))

    def _step_phase(self, offset: int) -> None:
        target = self.phase_selector.currentIndex() + offset
        if 0 <= target < self.phase_selector.count():
            self.phase_selector.setCurrentIndex(target)

    def _refresh_current_session(self) -> None:
        if self.session and self.session.phase:
            self.set_session(self.service.select_phase(self.session.phase.phase_id))

    def _save_orders(self, power_id, raw_text: str) -> None:
        try:
            self.service.update_orders(power_id, raw_text)
            self._refresh_current_session()
            self.statusBar().showMessage("Orders saved and validated", 2000)
        except Exception as exc:
            QMessageBox.critical(self, "Could not save orders", str(exc))

    def _set_final(self, power_id, value: bool) -> None:
        try:
            self.service.set_orders_final(power_id, value)
            self._refresh_current_session()
        except Exception as exc:
            QMessageBox.critical(self, "Could not change final state", str(exc))

    def _resolve(self) -> None:
        self.orders_workspace.resolve.setEnabled(False)
        self.statusBar().showMessage("Adjudicating phase…")
        task = BackgroundTask(lambda: self.service.resolve_and_advance(False))
        task.signals.succeeded.connect(self._resolved)
        task.signals.failed.connect(self._resolve_failed)
        self.thread_pool.start(task)

    def _resolved(self, result) -> None:
        self.orders_workspace.resolve.setEnabled(True)
        if isinstance(result, FinalisationRequired):
            names: list[str] = []
            if self.session and self.session.game:
                by_id = {power.id: power.name for power in self.session.game.map_definition.powers}
                names = [by_id[value] for value in result.unfinalised_powers]
            answer = QMessageBox.warning(
                self,
                "Orders are still open",
                "These powers are not final:\n\n" + "\n".join(names) + "\n\nResolve anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer is QMessageBox.StandardButton.Yes:
                self.orders_workspace.resolve.setEnabled(False)
                task = BackgroundTask(lambda: self.service.resolve_and_advance(True))
                task.signals.succeeded.connect(self._resolved)
                task.signals.failed.connect(self._resolve_failed)
                self.thread_pool.start(task)
            return
        if isinstance(result, AdvancedPhase):
            self.set_session(result.session, open_map=True)
            self.statusBar().showMessage("Phase resolved and recorded", 3000)

    def _resolve_failed(self, error) -> None:
        self.orders_workspace.resolve.setEnabled(True)
        self.statusBar().clearMessage()
        QMessageBox.critical(self, "Could not resolve phase", str(error))


def run_application(arguments: list[str] | None = None) -> int:
    app = QApplication(arguments or sys.argv)
    app.setApplicationName("Diplomacy Gamemaster")
    app.setOrganizationName("DiplomacyGamemaster")
    app.setStyleSheet(STYLE)
    window = ApplicationWindow(build_application())
    window.show()
    window.start()
    return app.exec()
