"""Heuristics helpers for mail-merge email composition."""

from __future__ import annotations

import re

from app.core.models import CellValue, ColumnInfo, RowData, SheetInfo

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def detect_email_columns(
    sheet: SheetInfo, rows: list[RowData], sample_k: int = 50
) -> list[ColumnInfo]:
    """Return columns that appear to contain email addresses.

    Each column is evaluated by sampling up to ``sample_k`` non-empty values from
    the provided rows. A column is considered an email column when at least 60%
    of the sampled values match the email pattern and there are at least three
    matching samples.
    """

    if sample_k <= 0 or not sheet.columns or not rows:
        return []

    detected: list[ColumnInfo] = []
    for column in sheet.columns:
        sampled = 0
        matches = 0
        for row in rows:
            if sampled >= sample_k:
                break
            value = row.values_by_key.get(column.key)
            if _is_empty_value(value):
                continue
            sampled += 1
            if _is_email_value(value):
                matches += 1
        if sampled == 0:
            continue
        if matches >= 3 and matches / sampled >= 0.6:
            detected.append(column)
    return detected


def _is_empty_value(value: CellValue) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _is_email_value(value: CellValue) -> bool:
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not candidate:
        return False
    return _EMAIL_PATTERN.fullmatch(candidate) is not None
