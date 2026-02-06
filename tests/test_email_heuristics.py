"""Tests for email_heuristics module."""

from __future__ import annotations

from mailmerge.core.email_heuristics import detect_email_columns
from mailmerge.core.models import ColumnInfo, RowData, SheetInfo


def _build_sheet() -> SheetInfo:
    return SheetInfo(
        name="Contacts",
        columns=[
            ColumnInfo(index=1, header="Email", key="Email", required=True),
            ColumnInfo(index=2, header="Department", key="Department", required=False),
        ],
        header_row_index=1,
    )


def _make_row(index: int, email_value: str | None, department: str = "Engineering") -> RowData:
    return RowData(
        row_index=index,
        values_by_key={"Email": email_value, "Department": department},
    )


def test_detect_email_columns_for_valid_majority() -> None:
    sheet = _build_sheet()
    rows = [
        _make_row(2, "ada@example.com"),
        _make_row(3, "grace@example.com"),
        _make_row(4, "not-an-email"),
        _make_row(5, "alan@example.com"),
    ]

    detected = detect_email_columns(sheet, rows)

    assert [column.key for column in detected] == ["Email"]


def test_detect_email_columns_requires_enough_samples_and_ratio() -> None:
    sheet = _build_sheet()
    too_few_samples = [
        _make_row(2, "ada@example.com"),
        _make_row(3, "grace@example.com"),
    ]

    assert detect_email_columns(sheet, too_few_samples) == []

    low_ratio_rows = [
        _make_row(2, "ada@example.com"),
        _make_row(3, "not-an-email"),
        _make_row(4, "still-not"),
        _make_row(5, "grace@example.com"),
        _make_row(6, "nope@example"),
    ]

    assert detect_email_columns(sheet, low_ratio_rows) == []


def test_detect_email_columns_trims_whitespace() -> None:
    sheet = _build_sheet()
    rows = [
        _make_row(2, "  ada@example.com "),
        _make_row(3, "\tgrace@example.com"),
        _make_row(4, "alan@example.com\n"),
        _make_row(5, "not-an-email"),
    ]

    detected = detect_email_columns(sheet, rows)

    assert [column.key for column in detected] == ["Email"]
