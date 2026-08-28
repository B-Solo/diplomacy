"""Small reusable text-editing widgets used by map configuration pages."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QToolButton,
    QWidget,
)


class YamlFindBar(QWidget):
    """Inline, wrapping search controls for a YAML text editor."""

    def __init__(self, editor: QPlainTextEdit, shortcut_parent: QWidget) -> None:
        super().__init__()
        self.editor = editor
        self._origin = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(4)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Find in YAML")
        self.query.setClearButtonEnabled(True)
        layout.addWidget(self.query, 1)
        previous = QToolButton()
        previous.setText("↑")
        previous.setToolTip("Previous match (Shift+Enter)")
        previous.clicked.connect(lambda: self.find_match(backward=True))
        layout.addWidget(previous)
        following = QToolButton()
        following.setText("↓")
        following.setToolTip("Next match (Enter)")
        following.clicked.connect(self.find_match)
        layout.addWidget(following)
        close = QToolButton()
        close.setText("×")
        close.setToolTip("Close find (Escape)")
        close.clicked.connect(self.close_find)
        layout.addWidget(close)

        self.find_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Find), shortcut_parent)
        self.find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.find_shortcut.activated.connect(self.show_find)
        self.previous_shortcut = QShortcut(QKeySequence("Shift+Return"), self.query)
        self.previous_shortcut.activated.connect(lambda: self.find_match(backward=True))
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.escape_shortcut.activated.connect(self.close_find)
        self.query.returnPressed.connect(self.find_match)
        self.query.textChanged.connect(lambda _text: self.find_match(from_origin=True))
        self.hide()

    def show_find(self) -> None:
        cursor = self.editor.textCursor()
        selected = cursor.selectedText()
        self._origin = cursor.selectionStart()
        if selected and "\u2029" not in selected:
            self.query.setText(selected)
        self.show()
        self.query.setFocus()
        self.query.selectAll()

    def close_find(self) -> None:
        self.hide()
        self.editor.setFocus()

    def find_match(self, backward: bool = False, from_origin: bool = False) -> None:
        query = self.query.text()
        if not query:
            self.query.setStyleSheet("")
            return
        if from_origin:
            cursor = QTextCursor(self.editor.document())
            cursor.setPosition(self._origin)
            self.editor.setTextCursor(cursor)
        flag = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        found = self.editor.find(query, flag)
        if not found:
            cursor = QTextCursor(self.editor.document())
            cursor.movePosition(
                QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start
            )
            self.editor.setTextCursor(cursor)
            found = self.editor.find(query, flag)
        self.query.setStyleSheet(
            "" if found else "QLineEdit { background: #f4d8d3; color: #551f1a; }"
        )


class DisplayNameEdit(QPlainTextEdit):
    """Multiline display-name editor whose unmodified Enter key applies."""

    apply_requested = Signal()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.apply_requested.emit()
            return
        super().keyPressEvent(event)
