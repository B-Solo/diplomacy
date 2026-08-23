"""Small QThreadPool adapter for slow coordinator calls."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal


class TaskSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(object)


class BackgroundTask(QRunnable):
    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = TaskSignals()

    def run(self) -> None:
        try:
            self.signals.succeeded.emit(self.function())
        except Exception as exc:
            self.signals.failed.emit(exc)
