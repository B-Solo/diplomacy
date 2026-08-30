"""Responsive power-panel order entry workspace."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from diplomacy_app.domain.models import IssueSeverity, PowerId

_ORDER_ENTRY_HEIGHT = 96
_ORDER_HEADER_HEIGHT = 34


def _preserved_html(text: str) -> str:
    """Escape text for rich display while preserving horizontal whitespace.

    :param text: One submitted or canonical order line.
    :return: Safe HTML whose spaces and tabs remain visible.
    """
    return escape(text).replace("\t", "    ").replace(" ", "&nbsp;")


class CanonicalOrdersView(QLabel):
    """Fixed-height rich order summary that opens its source editor when clicked."""

    activated = Signal()

    def __init__(self, content: str, parent=None) -> None:
        """Create a clickable canonical-order surface.

        :param content: Safe rich text describing every submitted order line.
        :param parent: Optional owning widget.
        """
        super().__init__(content, parent)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(_ORDER_ENTRY_HEIGHT)
        self.setStyleSheet(
            "background: #fffdf7; color: #171714; font-family: monospace; "
            "padding: 7px; border: 0; border-top: 1px solid #d8cfb8; "
            "border-bottom-left-radius: 5px; border-bottom-right-radius: 5px"
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Open the source editor in response to a primary-button click.

        :param event: Mouse press delivered to the canonical-order surface.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mousePressEvent(event)


class PowerPanel(QFrame):
    save_requested = Signal(object, str)
    final_requested = Signal(object, bool)
    editing_finished = Signal()
    tab_requested = Signal(object, bool)

    def __init__(
        self,
        power,
        submission,
        requirement,
        editable: bool,
        finalisation_enabled: bool,
        parent=None,
    ) -> None:
        """Build one power's order entry and optional finalisation controls.

        :param power: Power represented by this panel.
        :param submission: Existing order submission, when one has been saved.
        :param requirement: Orders required from the power in this phase.
        :param editable: Whether the selected phase is editable.
        :param finalisation_enabled: Whether this game tracks final order submissions.
        :param parent: Optional owning widget.
        """
        super().__init__(parent)
        self.power = power
        self.submission = submission
        self.requirement = requirement
        self.editable = editable and requirement.requires_submission
        self.setObjectName("powerPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setStyleSheet(
            f"QFrame#powerPanel {{ border: 1px solid #c9bea3; "
            f"border-top: 4px solid {power.colour}; background: #fbf7eb; "
            "color: #292820; border-radius: 6px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header_widget = QWidget()
        header_widget.setFixedHeight(_ORDER_HEADER_HEIGHT)
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(8, 2, 7, 2)
        header.setSpacing(5)
        name = QLabel(power.name)
        name.setStyleSheet("font-size: 11pt; font-weight: 700; border: 0")
        header.addWidget(name)
        header.addStretch()
        issues = self._issues()
        if issues:
            warning = QPushButton("⚠")
            warning.setToolTip("Show order issues")
            warning.clicked.connect(self._toggle_issues)
            header.addWidget(warning)
        self.final: QCheckBox | None = None
        if finalisation_enabled:
            self.final = QCheckBox("Orders final")
            self.final.setEnabled(self.editable)
            self.final.setChecked(
                not requirement.requires_submission or bool(submission and submission.is_final)
            )
            self.final.toggled.connect(self._final_toggled)
            header.addWidget(self.final)
        layout.addWidget(header_widget)
        if not requirement.requires_submission:
            no_orders = QLabel("No orders required")
            no_orders.setProperty("muted", True)
            no_orders.setStyleSheet(
                "font-style: italic; border: 0; border-top: 1px solid #d8cfb8; "
                "padding: 8px; background: #fffdf7"
            )
            layout.addWidget(no_orders)
            self.editor = None
            self.issue_box = None
            return
        self.stack = QStackedWidget()
        self.canonical = CanonicalOrdersView(self._canonical_html())
        self.canonical.activated.connect(self.begin_editing)
        self.stack.addWidget(self.canonical)
        self.editor = QPlainTextEdit(submission.raw_text if submission else "")
        self.editor.setPlaceholderText("One order per line")
        self.editor.setStyleSheet(
            "QPlainTextEdit { background: #fffdf7; color: #171714; "
            "font-family: monospace; padding: 6px; border: 0; "
            "border-top: 1px solid #d8cfb8; border-bottom-left-radius: 5px; "
            "border-bottom-right-radius: 5px; }"
        )
        self.editor.setFixedHeight(_ORDER_ENTRY_HEIGHT)
        self.editor.installEventFilter(self)
        self.stack.addWidget(self.editor)
        self.stack.setFixedHeight(_ORDER_ENTRY_HEIGHT)
        layout.addWidget(self.stack)
        self.issue_box = QLabel("\n".join(f"Line {line}: {message}" for line, message in issues))
        self.issue_box.setWordWrap(True)
        self.issue_box.setStyleSheet(
            "background: #f6dfc0; color: #713d22; padding: 8px; border: 1px solid #c99b63"
        )
        self.issue_box.setVisible(False)
        layout.addWidget(self.issue_box)
        self.editor.textChanged.connect(self._edited)

    def begin_editing(self) -> None:
        """Reveal and focus the source editor when this panel is editable."""
        if not self.editable or self.editor is None:
            return
        self.stack.setCurrentWidget(self.editor)
        self.editor.setFocus(Qt.FocusReason.MouseFocusReason)

    def _issues(self) -> list[tuple[int, str]]:
        result: list[tuple[int, str]] = []
        if not self.submission:
            return result
        for line in self.submission.lines:
            for issue in line.candidate.parser_issues:
                if issue.severity is IssueSeverity.ERROR:
                    result.append((line.candidate.source.number, issue.message))
            if line.validation:
                for issue in line.validation.issues:
                    result.append((line.candidate.source.number, issue.message))
        return result

    def _canonical_html(self) -> str:
        """Render recognised and unparseable submission lines for the summary.

        :return: Safe rich text with unparseable source lines marked in red.
        """
        if not self.submission or not self.submission.lines:
            return "Click to enter orders…"
        lines: list[str] = []
        for line in self.submission.lines:
            candidate = line.candidate
            if candidate.canonical_text is not None:
                lines.append(_preserved_html(candidate.canonical_text))
            else:
                source = _preserved_html(candidate.source.text)
                lines.append(f'<span style="color:#a32620; font-weight:700">{source} (??)</span>')
        return "<br>".join(lines)

    def _toggle_issues(self) -> None:
        if self.issue_box:
            self.issue_box.setVisible(not self.issue_box.isVisible())

    def _edited(self) -> None:
        """Mark the power's orders open until the edited text is validated."""
        if self.final is not None:
            self.final.blockSignals(True)
            self.final.setChecked(False)
            self.final.blockSignals(False)

    def _save(self) -> None:
        if self.editor is not None:
            self.save_requested.emit(self.power.id, self.editor.toPlainText())

    def _final_toggled(self, value: bool) -> None:
        if self.editable:
            self.final_requested.emit(self.power.id, value)

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.editor
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
        ):
            reverse = event.key() == Qt.Key.Key_Backtab or bool(
                event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            )
            self.tab_requested.emit(self.power.id, reverse)
            return True
        if watched is self.editor and event.type() == QEvent.Type.FocusOut:
            saved_text = self.submission.raw_text if self.submission else ""
            if self.editor.toPlainText() != saved_text:
                self._save()
            self.stack.setCurrentIndex(0)
            self.editing_finished.emit()
        return super().eventFilter(watched, event)


class OrdersWorkspace(QWidget):
    save_requested = Signal(object, str)
    final_requested = Signal(object, bool)
    editing_finished = Signal()
    preview_requested = Signal()
    resolve_requested = Signal()
    resolve_anyway_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.phase_label = QLabel()
        self.phase_label.setStyleSheet("font: 700 14pt Georgia, serif")
        controls.addWidget(self.phase_label)
        controls.addStretch()
        self.unfinalised = QCheckBox("Unfinalised only")
        self.unfinalised.toggled.connect(self._apply_filter)
        controls.addWidget(self.unfinalised)
        self.final_count = QLabel()
        controls.addWidget(self.final_count)
        self.preview = QPushButton("Preview orders on map")
        self.preview.setToolTip(
            "Show order arrows and markers over the current position without resolving the phase"
        )
        self.preview.clicked.connect(self.preview_requested.emit)
        controls.addWidget(self.preview)
        self.resolve = QPushButton("Resolve and advance")
        self.resolve.setProperty("primary", True)
        self.resolve.clicked.connect(self.resolve_requested)
        controls.addWidget(self.resolve)
        outer.addLayout(controls)
        self.syntax_examples = QLabel(
            "Examples — replace the locations:  "
            "A London H   ·   A London - Wales   ·   A London to Wales   ·   "
            "F North Sea S A Yorkshire - London\n"
            "Retreat: A London R Wales   ·   Build: A London B   ·   "
            "Disband: A London D   ·   Waive"
        )
        self.syntax_examples.setWordWrap(True)
        self.syntax_examples.setProperty("muted", True)
        self.syntax_examples.setStyleSheet(
            "background: #f6f1e3; border: 1px solid #d8cfb8; "
            "border-radius: 4px; padding: 5px 8px; font-family: monospace"
        )
        outer.addWidget(self.syntax_examples)
        self.confirmation = QFrame()
        self.confirmation.setStyleSheet(
            "background: #f6dfc0; color: #713d22; border: 1px solid #c99b63; border-radius: 4px"
        )
        confirmation_layout = QHBoxLayout(self.confirmation)
        self.confirmation_text = QLabel()
        self.confirmation_text.setWordWrap(True)
        confirmation_layout.addWidget(self.confirmation_text, 1)
        cancel = QPushButton("Keep editing")
        cancel.clicked.connect(lambda: self.confirmation.setVisible(False))
        confirmation_layout.addWidget(cancel)
        proceed = QPushButton("Resolve anyway")
        proceed.setProperty("danger", True)
        proceed.clicked.connect(self._confirm_resolve)
        confirmation_layout.addWidget(proceed)
        self.confirmation.setVisible(False)
        outer.addWidget(self.confirmation)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.container)
        outer.addWidget(self.scroll_area, 1)
        self.panels: list[PowerPanel] = []
        self.finalisation_enabled = False

    def pending_order_texts(self) -> tuple[tuple[PowerId, str], ...]:
        """Take order text that has changed since the displayed session was loaded.

        :return: Power identifiers and their currently entered raw order text.
        """
        pending: list[tuple[PowerId, str]] = []
        for panel in self.panels:
            if panel.editor is None:
                continue
            raw_text = panel.editor.toPlainText()
            saved_text = panel.submission.raw_text if panel.submission else ""
            if raw_text == saved_text:
                continue
            pending.append((panel.power.id, raw_text))
        return tuple(pending)

    def focused_editor_power(self) -> PowerId | None:
        """Return the power whose source editor currently owns keyboard focus."""
        for panel in self.panels:
            if panel.editor is not None and panel.editor.hasFocus():
                return panel.power.id
        return None

    def begin_editing(self, power_id: PowerId) -> None:
        """Focus a power's source editor after the workspace has refreshed.

        :param power_id: Power whose editor should remain active.
        """
        panel = next((item for item in self.panels if item.power.id == power_id), None)
        if panel is not None:
            panel.begin_editing()

    def _panel_editing_finished(self) -> None:
        """Defer canonical refresh until the current focus event is complete."""
        QTimer.singleShot(0, self.editing_finished.emit)

    def show_unfinalised_confirmation(self, names: list[str]) -> None:
        self.confirmation_text.setText(
            "Orders are still open for " + ", ".join(names) + ". Resolve anyway?"
        )
        self.confirmation.setVisible(True)

    def _confirm_resolve(self) -> None:
        self.confirmation.setVisible(False)
        self.resolve_anyway_requested.emit()

    def set_session(self, session) -> None:
        for panel in self.panels:
            panel.editing_finished.disconnect()
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.panels = []
        self.confirmation.setVisible(False)
        if not session.game or not session.phase or not session.phase_requirements:
            return
        self.phase_label.setText(session.phase.phase_id.label)
        editable = session.phase.phase_id == session.game.current_phase
        self.finalisation_enabled = session.game.settings.require_order_finalisation
        self.unfinalised.setVisible(self.finalisation_enabled)
        self.final_count.setVisible(self.finalisation_enabled)
        self.resolve.setVisible(editable)
        complete = 0
        for index, power in enumerate(session.game.map_definition.powers):
            requirement = session.phase_requirements.by_power[power.id]
            submission = session.phase.submissions.get(power.id)
            panel = PowerPanel(
                power,
                submission,
                requirement,
                editable,
                self.finalisation_enabled,
            )
            panel.save_requested.connect(self.save_requested)
            panel.final_requested.connect(self.final_requested)
            panel.editing_finished.connect(self._panel_editing_finished)
            panel.tab_requested.connect(self._tab_requested)
            self.panels.append(panel)
            self.grid.addWidget(panel, index // 2, index % 2)
            if not requirement.requires_submission or (submission and submission.is_final):
                complete += 1
        if self.finalisation_enabled:
            self.final_count.setText(f"{complete} of {len(self.panels)} final")
        self._apply_filter()

    def _tab_requested(self, power_id: PowerId, reverse: bool) -> None:
        """Move focus to the adjacent editable power order editor.

        :param power_id: Power whose editor currently owns keyboard focus.
        :param reverse: Whether focus should move toward the preceding editor.
        """
        editable = [panel for panel in self.panels if panel.editor is not None and panel.editable]
        if len(editable) < 2:
            return
        current = next(
            (index for index, panel in enumerate(editable) if panel.power.id == power_id),
            None,
        )
        if current is None:
            return
        step = -1 if reverse else 1
        editable[(current + step) % len(editable)].begin_editing()

    def _apply_filter(self) -> None:
        for panel in self.panels:
            is_final = bool(panel.final and panel.final.isChecked())
            panel.setVisible(
                not self.finalisation_enabled or not self.unfinalised.isChecked() or not is_final
            )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        columns = 2 if self.width() >= 850 else 1
        for index, panel in enumerate(self.panels):
            self.grid.removeWidget(panel)
            self.grid.addWidget(panel, index // columns, index % columns)
