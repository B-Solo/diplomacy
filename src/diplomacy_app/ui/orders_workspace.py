"""Responsive power-panel order entry workspace."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from diplomacy_app.domain.models import IssueSeverity


class PowerPanel(QFrame):
    save_requested = Signal(object, str)
    final_requested = Signal(object, bool)

    def __init__(self, power, submission, requirement, editable: bool, parent=None) -> None:
        super().__init__(parent)
        self.power = power
        self.submission = submission
        self.requirement = requirement
        self.editable = editable and requirement.requires_submission
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{ border-top: 4px solid {power.colour}; background: #fbf7eb; border-radius: 6px; }}"
        )
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        name = QLabel(power.name)
        name.setStyleSheet("font-size: 12pt; font-weight: 700; border: 0")
        header.addWidget(name)
        header.addStretch()
        issues = self._issues()
        if issues:
            warning = QPushButton("⚠")
            warning.setToolTip("Show order issues")
            warning.clicked.connect(self._toggle_issues)
            header.addWidget(warning)
        self.final = QCheckBox("Orders final")
        self.final.setEnabled(self.editable)
        self.final.setChecked(
            not requirement.requires_submission or bool(submission and submission.is_final)
        )
        self.final.toggled.connect(self._final_toggled)
        header.addWidget(self.final)
        layout.addLayout(header)
        if not requirement.requires_submission:
            no_orders = QLabel("No orders required")
            no_orders.setProperty("muted", True)
            no_orders.setStyleSheet("font-style: italic; border: 0")
            layout.addWidget(no_orders)
            self.editor = None
            self.issue_box = None
            return
        self.stack = QStackedWidget()
        canonical = QPushButton(self._canonical_text())
        canonical.setFlat(True)
        canonical.setCursor(Qt.CursorShape.PointingHandCursor)
        canonical.setStyleSheet(
            "text-align: left; font-family: Consolas, monospace; padding: 8px; border: 0"
        )
        canonical.clicked.connect(lambda: self.stack.setCurrentIndex(1) if self.editable else None)
        self.stack.addWidget(canonical)
        self.editor = QPlainTextEdit(submission.raw_text if submission else "")
        self.editor.setPlaceholderText("One order per line")
        self.editor.setMinimumHeight(105)
        self.editor.installEventFilter(self)
        self.stack.addWidget(self.editor)
        layout.addWidget(self.stack)
        self.issue_box = QLabel("\n".join(f"Line {line}: {message}" for line, message in issues))
        self.issue_box.setWordWrap(True)
        self.issue_box.setStyleSheet(
            "background: #f6dfc0; color: #713d22; padding: 8px; border: 1px solid #c99b63"
        )
        self.issue_box.setVisible(False)
        layout.addWidget(self.issue_box)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._save)
        self.editor.textChanged.connect(self._edited)

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

    def _canonical_text(self) -> str:
        if not self.submission or not self.submission.lines:
            return "Click to enter orders…"
        return "\n".join(
            line.candidate.canonical_text or f"?  {line.candidate.source.text}"
            for line in self.submission.lines
        )

    def _toggle_issues(self) -> None:
        if self.issue_box:
            self.issue_box.setVisible(not self.issue_box.isVisible())

    def _edited(self) -> None:
        self.final.blockSignals(True)
        self.final.setChecked(False)
        self.final.blockSignals(False)
        self.timer.start()

    def _save(self) -> None:
        if self.editor is not None:
            self.save_requested.emit(self.power.id, self.editor.toPlainText())

    def _final_toggled(self, value: bool) -> None:
        if self.editable:
            self.final_requested.emit(self.power.id, value)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.editor and event.type() == QEvent.Type.FocusOut:
            if self.timer.isActive():
                self.timer.stop()
                self._save()
            self.stack.setCurrentIndex(0)
        return super().eventFilter(watched, event)


class OrdersWorkspace(QWidget):
    save_requested = Signal(object, str)
    final_requested = Signal(object, bool)
    resolve_requested = Signal()

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
        self.resolve = QPushButton("Resolve and advance")
        self.resolve.setProperty("primary", True)
        self.resolve.clicked.connect(self.resolve_requested)
        controls.addWidget(self.resolve)
        outer.addLayout(controls)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.container)
        outer.addWidget(self.scroll_area, 1)
        self.panels: list[PowerPanel] = []

    def set_session(self, session) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.panels = []
        if not session.game or not session.phase or not session.phase_requirements:
            return
        self.phase_label.setText(session.phase.phase_id.label)
        editable = session.phase.phase_id == session.game.current_phase
        self.resolve.setVisible(editable)
        complete = 0
        for index, power in enumerate(session.game.map_definition.powers):
            requirement = session.phase_requirements.by_power[power.id]
            submission = session.phase.submissions.get(power.id)
            panel = PowerPanel(power, submission, requirement, editable)
            panel.save_requested.connect(self.save_requested)
            panel.final_requested.connect(self.final_requested)
            self.panels.append(panel)
            self.grid.addWidget(panel, index // 2, index % 2)
            if not requirement.requires_submission or (submission and submission.is_final):
                complete += 1
        self.final_count.setText(f"{complete} of {len(self.panels)} final")
        self._apply_filter()

    def _apply_filter(self) -> None:
        for panel in self.panels:
            is_final = panel.final.isChecked()
            panel.setVisible(not self.unfinalised.isChecked() or not is_final)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        columns = 2 if self.width() >= 850 else 1
        for index, panel in enumerate(self.panels):
            self.grid.removeWidget(panel)
            self.grid.addWidget(panel, index // columns, index % columns)
