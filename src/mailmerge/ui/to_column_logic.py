"""Helpers for selecting recipient columns in the UI."""

from __future__ import annotations

from mailmerge.core.email_heuristics import detect_email_columns
from mailmerge.core.models import ColumnInfo, RowData, SheetInfo

_WARNING_NO_EMAIL = "No column strongly resembles email addresses."


def choose_to_columns(
    sheet: SheetInfo,
    rows: list[RowData],
) -> tuple[list[ColumnInfo], list[str]]:
    """Return candidate recipient columns and warnings for the UI.

    The helper prefers columns that resemble email addresses. If none are
    detected, it returns all columns and includes a warning message.
    """

    detected = _detect_email_columns(sheet, rows)
    if detected:
        return detected, []
    return list(sheet.columns), [_WARNING_NO_EMAIL]


def _detect_email_columns(sheet: SheetInfo, rows: list[RowData]) -> list[ColumnInfo]:
    """Invoke the shared email column detection helper."""

    try:
        detected = detect_email_columns(sheet, rows, sample_k=50)
    except TypeError:
        detected = detect_email_columns(sheet, rows)
    return list(detected)
