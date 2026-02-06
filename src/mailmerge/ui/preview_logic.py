"""UI helper functions for preview rendering without Qt dependencies."""

from __future__ import annotations

from collections.abc import Callable

from mailmerge.core.models import RowResult

_EMPTY_BODY_MESSAGE = "No HTML output generated."


def apply_preview_result_to_viewer(
    result: RowResult,
    *,
    set_subject: Callable[[str], None],
    set_html: Callable[[str], None],
    empty_html: Callable[[str], str],
) -> None:
    """Apply preview results to UI setter callbacks.

    This helper keeps the preview pipeline testable without Qt widget imports.
    """
    subject_text = result.rendered_subject or ""
    set_subject(subject_text)
    html = result.rendered_body if result.rendered_body else empty_html(_EMPTY_BODY_MESSAGE)
    set_html(html)
