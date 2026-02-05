"""Compatibility shim for ui/main_window.py.

The real GUI implementation lives in app.ui.main_window and uses
QProgressDialog to report run progress.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow as MainWindow


def __getattr__(name: str) -> Any:
    """Lazily resolve attributes from app.ui.main_window."""
    if name == "MainWindow":
        from app.ui.main_window import MainWindow as main_window

        return main_window
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["MainWindow"]
