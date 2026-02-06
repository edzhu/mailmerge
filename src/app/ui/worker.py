"""Background worker helpers for the PySide6 GUI."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    """Signals emitted by controller workers."""

    started = Signal()
    finished = Signal()
    result = Signal(object)
    error = Signal(str)


class ControllerWorker(QRunnable):
    """Run a callable in a QThreadPool without blocking the UI."""

    def __init__(
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        self.signals.started.emit()
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:
            logger.exception("Worker execution failed.")
            self.signals.error.emit(str(exc))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
