"""Compatibility shim for ui/preview_dialog.py.

The real GUI implementation lives in app.ui.preview_dialog.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.ui.preview_dialog import PreviewDialog as PreviewDialog


def __getattr__(name: str) -> Any:
    """Lazily resolve attributes from app.ui.preview_dialog."""
    if name == "PreviewDialog":
        from app.ui.preview_dialog import PreviewDialog as preview_dialog

        return preview_dialog
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["PreviewDialog"]
