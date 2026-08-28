"""Main desktop window and application entry point."""

from __future__ import annotations

import signal
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from diplomacy_app.application import build_application
from diplomacy_app.domain.models import (
    AdvancedPhase,
    DisplayMode,
    FinalisationRequired,
    GameLocation,
)
from diplomacy_app.ui.background_tasks import BackgroundTask
from diplomacy_app.ui.map_manager_workspace import MapManagerWorkspace
from diplomacy_app.ui.map_wizard import MapWizard
from diplomacy_app.ui.map_workspace import MapWorkspace
from diplomacy_app.ui.new_game_workspace import NewGameWorkspace
from diplomacy_app.ui.orders_workspace import OrdersWorkspace
from diplomacy_app.ui.style import STYLE, light_palette


class ApplicationWindow(QMainWindow):
    def __init__(self, service, settings: QSettings | None = None) -> None:
        super().__init__()
        self.service = service
        self.session = None
        self._pending_game_deletion: tuple[GameLocation, str] | None = None
        self.thread_pool = QThreadPool.globalInstance()
        self.setWindowTitle("Diplomacy Gamemaster")
        self.resize(1280, 840)
        self.setMinimumSize(860, 620)
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        self.close_window_action = QAction("Close window", self)
        self.close_window_action.setShortcuts(QKeySequence.StandardKey.Close)
        self.close_window_action.triggered.connect(self.close)
        self.addAction(self.close_window_action)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header())
        self.stack = QStackedWidget()
        self.welcome = self._welcome_page()
        self.map_workspace = MapWorkspace(service, settings=settings)
        self.orders_workspace = OrdersWorkspace()
        self.orders_workspace.save_requested.connect(self._save_orders)
        self.orders_workspace.final_requested.connect(self._set_final)
        self.orders_workspace.preview_requested.connect(self._preview_orders)
        self.orders_workspace.resolve_requested.connect(self._resolve)
        self.orders_workspace.resolve_anyway_requested.connect(self._resolve_anyway)
        self.map_workspace.message.connect(self._show_error)
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.map_workspace)
        self.stack.addWidget(self.orders_workspace)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self._season_bar())
        self.setCentralWidget(root)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().messageChanged.connect(
            lambda message: self.statusBar().setVisible(bool(message))
        )
        self.statusBar().hide()

    def _header(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #33483d; color: #fffaf0; border: 0; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 3, 6, 3)
        layout.setSpacing(5)
        brand = QLabel("⚜  Diplomacy")
        brand.setStyleSheet("font: 700 14pt Georgia, serif; color: #f7edcf")
        layout.addWidget(brand)
        self.game_button = QPushButton("No game open")
        self.game_button.setStyleSheet(
            "color: #fffaf0; background: transparent; border-color: #829487"
        )
        self.game_button.clicked.connect(self._show_game_choices)
        layout.addWidget(self.game_button)
        layout.addStretch()
        workspace_label = QLabel("Workspace")
        workspace_label.setStyleSheet(
            "color: #cbd7cf; font-size: 8pt; font-weight: 700; text-transform: uppercase"
        )
        layout.addWidget(workspace_label)
        self.tabs = QTabBar()
        self.tabs.setObjectName("primaryWorkspaceTabs")
        self.tabs.setAccessibleName("Primary workspace")
        self.tabs.setDrawBase(False)
        self.tabs.setStyleSheet(
            "QTabBar#primaryWorkspaceTabs::tab {"
            " background: #263a31; color: #fffaf0; border: 1px solid #829487;"
            " border-radius: 4px; min-width: 82px; padding: 7px 14px;"
            " font-size: 10pt; font-weight: 700; margin-left: 3px; }"
            "QTabBar#primaryWorkspaceTabs::tab:hover:!selected {"
            " background: #50675a; border-color: #b6c3ba; }"
            "QTabBar#primaryWorkspaceTabs::tab:selected {"
            " background: #fffaf0; color: #20352b; border-color: #fffaf0; }"
        )
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
        self.game_map_placement_button = QPushButton("Adjust current map placement…")
        self.game_map_placement_button.clicked.connect(self._edit_game_map_placement)
        self.game_map_placement_button.setVisible(False)
        buttons.addWidget(self.game_map_placement_button)
        layout.addLayout(buttons)
        self.return_button = QPushButton("Return to current game")
        self.return_button.clicked.connect(self._return_to_context)
        self.return_button.setVisible(False)
        layout.addWidget(self.return_button)

        self.delete_confirmation = QFrame()
        self.delete_confirmation.setStyleSheet(
            "QFrame { background: #f3ddd8; border: 1px solid #b66a61; border-radius: 4px; }"
        )
        confirmation_layout = QHBoxLayout(self.delete_confirmation)
        self.delete_confirmation_text = QLabel()
        self.delete_confirmation_text.setWordWrap(True)
        confirmation_layout.addWidget(self.delete_confirmation_text, 1)
        cancel_delete = QPushButton("Cancel")
        cancel_delete.clicked.connect(self._cancel_game_deletion)
        confirmation_layout.addWidget(cancel_delete)
        self.confirm_delete_game = QPushButton("Delete game permanently")
        self.confirm_delete_game.setProperty("danger", True)
        self.confirm_delete_game.clicked.connect(self._confirm_game_deletion)
        confirmation_layout.addWidget(self.confirm_delete_game)
        self.delete_confirmation.setVisible(False)
        layout.addWidget(self.delete_confirmation)

        self.recent_layout = QVBoxLayout()
        layout.addLayout(self.recent_layout)
        return page

    def _season_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(
            "QFrame { background: #f6f1e3; color: #292820; border-top: 1px solid #b7ae97; }"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
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
            self._show_error(f"Could not reopen last game: {exc}")
            self.session = None
            self.stack.setCurrentWidget(self.welcome)

    def set_session(self, session, *, open_map: bool = False) -> None:
        self.session = session
        game = session.game
        self.tabs.setVisible(game is not None)
        self.season_bar.setVisible(game is not None)
        if game is None:
            self.stack.setCurrentWidget(self.welcome)
            self.game_button.setText("No game open")
            self.return_button.setVisible(False)
            self.game_map_placement_button.setVisible(False)
            self._populate_recent(session)
            return
        self.game_button.setText(game.name + "  ▾")
        self.return_button.setText(f"Return to {game.name}")
        self.return_button.setVisible(True)
        self.game_map_placement_button.setVisible(True)
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
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(5)
            open_recent = QPushButton(f"{recent.name}  —  {recent.current_phase.label}")
            open_recent.clicked.connect(
                lambda _checked=False, location=recent.location: self._open_location(location)
            )
            row_layout.addWidget(open_recent, 1)
            delete_recent = QPushButton("Delete…")
            delete_recent.setProperty("danger", True)
            delete_recent.clicked.connect(
                lambda _checked=False, location=recent.location, name=recent.name: (
                    self._request_game_deletion(location, name)
                )
            )
            row_layout.addWidget(delete_recent)
            self.recent_layout.addWidget(row)

    def _request_game_deletion(self, location: GameLocation, name: str) -> None:
        self._pending_game_deletion = (location, name)
        self.delete_confirmation_text.setText(
            f'Delete "{name}" permanently? This removes the complete game folder at '
            f"{location.path} and cannot be undone."
        )
        self.delete_confirmation.setVisible(True)

    def _cancel_game_deletion(self) -> None:
        self._pending_game_deletion = None
        self.delete_confirmation.setVisible(False)

    def _confirm_game_deletion(self) -> None:
        if self._pending_game_deletion is None:
            return
        location, name = self._pending_game_deletion
        try:
            session = self.service.delete_game(location)
        except Exception as exc:
            self._show_error(f"Could not delete game: {exc}")
            return
        self._cancel_game_deletion()
        self.set_session(session)
        self._show_game_choices()
        self.statusBar().showMessage(f"Deleted game {name}", 3000)

    def _tab_changed(self, index: int) -> None:
        if not self.session or not self.session.game:
            return
        self.stack.setCurrentWidget(self.map_workspace if index == 0 else self.orders_workspace)

    def _show_game_choices(self) -> None:
        self.tabs.setVisible(False)
        self.season_bar.setVisible(False)
        self.stack.setCurrentWidget(self.welcome)
        if self.session:
            self._populate_recent(self.session)

    def _open_game(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open game folder")
        if folder:
            self._open_location(GameLocation(Path(folder).resolve()))

    def _open_location(self, location) -> None:
        try:
            self.set_session(self.service.open_game(location), open_map=True)
        except Exception as exc:
            self._show_error(f"Could not open game: {exc}")

    def _new_game(self) -> None:
        workspace = NewGameWorkspace(self.service)
        workspace.cancelled.connect(lambda: self._close_setup_workspace(workspace))
        workspace.created.connect(self._game_created)
        workspace.edit_requested.connect(lambda draft: self._open_map_wizard(draft, workspace))
        self._open_setup_workspace(workspace)

    def _configure_maps(self) -> None:
        workspace = MapManagerWorkspace(self.service)
        workspace.cancelled.connect(lambda: self._close_setup_workspace(workspace))
        workspace.edit_requested.connect(lambda draft: self._open_map_wizard(draft, workspace))
        self._open_setup_workspace(workspace)

    def _edit_game_map_placement(self) -> None:
        try:
            draft = self.service.begin_game_map_placement()
            wizard = MapWizard(self.service, draft, game_placement_only=True)
            wizard.cancelled.connect(lambda: self._close_setup_workspace(wizard))
            wizard.saved.connect(lambda session: self._game_map_placement_saved(wizard, session))
            self._open_setup_workspace(wizard)
        except Exception as exc:
            self._show_error(f"Could not edit game map placement: {exc}")

    def _open_setup_workspace(self, workspace: QWidget) -> None:
        self.stack.addWidget(workspace)
        self.stack.setCurrentWidget(workspace)
        self.tabs.setVisible(False)
        self.season_bar.setVisible(False)

    def _close_setup_workspace(self, workspace: QWidget) -> None:
        self.stack.removeWidget(workspace)
        workspace.deleteLater()
        self._return_to_context()

    def _open_map_wizard(self, draft, origin: QWidget) -> None:
        wizard = MapWizard(self.service, draft)
        wizard.cancelled.connect(lambda: self._close_wizard(wizard, origin))
        wizard.saved.connect(lambda definition: self._map_saved(wizard, origin, definition))
        self._open_setup_workspace(wizard)

    def _close_wizard(self, wizard: QWidget, origin: QWidget) -> None:
        self.stack.removeWidget(wizard)
        wizard.deleteLater()
        self.stack.setCurrentWidget(origin)

    def _map_saved(self, wizard: QWidget, origin: QWidget, definition) -> None:
        if hasattr(origin, "map_saved"):
            origin.map_saved(definition)
        elif hasattr(origin, "refresh"):
            origin.refresh(definition.id)
        self._close_wizard(wizard, origin)
        self.statusBar().showMessage(f"Saved reusable map {definition.name}", 3000)

    def _game_map_placement_saved(self, wizard: QWidget, session) -> None:
        self.stack.removeWidget(wizard)
        wizard.deleteLater()
        self.set_session(session, open_map=True)
        self.statusBar().showMessage("Saved this game's map placement", 3000)

    def _game_created(self, session) -> None:
        workspace = self.stack.currentWidget()
        self.stack.removeWidget(workspace)
        workspace.deleteLater()
        self.set_session(session, open_map=True)

    def _return_to_context(self) -> None:
        if self.session and self.session.game:
            self.set_session(self.session)
        else:
            self.tabs.setVisible(False)
            self.season_bar.setVisible(False)
            self.stack.setCurrentWidget(self.welcome)

    def _phase_selected(self) -> None:
        phase = self.phase_selector.currentData()
        if phase is None or not self.session or phase == self.session.phase.phase_id:
            return
        try:
            self.set_session(self.service.select_phase(phase))
        except Exception as exc:
            self._show_error(f"Could not open phase: {exc}")

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
            self._show_error(f"Could not save orders: {exc}")

    def _set_final(self, power_id, value: bool) -> None:
        try:
            self.service.set_orders_final(power_id, value)
            self._refresh_current_session()
        except Exception as exc:
            self._show_error(f"Could not change final state: {exc}")

    def _preview_orders(self) -> None:
        """Save pending order text and show its overlays on the current position."""
        if not self.session or not self.session.phase:
            return
        phase_id = self.session.phase.phase_id
        try:
            for power_id, raw_text in self.orders_workspace.pending_order_texts():
                self.service.update_orders(power_id, raw_text)
            session = self.service.select_phase(phase_id)
            self.map_workspace.mode.setCurrentIndex(
                self.map_workspace.mode.findData(DisplayMode.ORDERS)
            )
            self.set_session(session, open_map=True)
            self.statusBar().showMessage("Previewing orders on the current position", 3000)
        except Exception as exc:
            self._refresh_current_session()
            self._show_error(f"Could not preview orders: {exc}")

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
            self.orders_workspace.show_unfinalised_confirmation(names)
            return
        if isinstance(result, AdvancedPhase):
            self.set_session(result.session, open_map=True)
            self.statusBar().showMessage("Phase resolved and recorded", 3000)

    def _resolve_failed(self, error) -> None:
        self.orders_workspace.resolve.setEnabled(True)
        self._show_error(f"Could not resolve phase: {error}")

    def _resolve_anyway(self) -> None:
        self.orders_workspace.resolve.setEnabled(False)
        task = BackgroundTask(lambda: self.service.resolve_and_advance(True))
        task.signals.succeeded.connect(self._resolved)
        task.signals.failed.connect(self._resolve_failed)
        self.thread_pool.start(task)

    def _show_error(self, text: str) -> None:
        self.statusBar().showMessage(text, 8000)


def _quit_on_interrupt(app, _signum: int, _frame) -> None:
    app.quit()


def run_application(arguments: list[str] | None = None) -> int:
    app = QApplication(arguments or sys.argv)
    app.setApplicationName("Diplomacy Gamemaster")
    app.setOrganizationName("DiplomacyGamemaster")
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setStyleSheet(STYLE)
    window = ApplicationWindow(build_application())
    window.showMaximized()
    window.start()
    previous_interrupt_handler = signal.getsignal(signal.SIGINT)
    signal.signal(
        signal.SIGINT,
        lambda signum, frame: _quit_on_interrupt(app, signum, frame),
    )
    interrupt_timer = QTimer(app)
    interrupt_timer.setInterval(100)
    interrupt_timer.timeout.connect(lambda: None)
    interrupt_timer.start()
    try:
        return app.exec()
    finally:
        interrupt_timer.stop()
        signal.signal(signal.SIGINT, previous_interrupt_handler)
