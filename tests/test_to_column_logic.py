"""Tests for the to-column selection helper."""

from __future__ import annotations

from app.core.models import ColumnInfo, RowData, SheetInfo
from app.ui.to_column_logic import choose_to_columns

_WARNING_NO_EMAIL = "No column strongly resembles email addresses."


def _make_row(index: int, values: dict[str, str]) -> RowData:
    return RowData(row_index=index, values_by_key=values)


def test_choose_to_columns_prefers_detected_email_column() -> None:
    sheet = SheetInfo(
        name="联系人",
        columns=[
            ColumnInfo(index=1, header="邮箱", key="邮箱", required=True),
            ColumnInfo(index=2, header="姓名", key="姓名", required=False),
        ],
        header_row_index=1,
    )
    rows = [
        _make_row(2, {"邮箱": "ada@example.com", "姓名": "Ada"}),
        _make_row(3, {"邮箱": "grace@example.com", "姓名": "Grace"}),
        _make_row(4, {"邮箱": "not-an-email", "姓名": "Alan"}),
        _make_row(5, {"邮箱": "linus@example.com", "姓名": "Linus"}),
    ]

    selected, warnings = choose_to_columns(sheet, rows)

    assert [column.key for column in selected] == ["邮箱"]
    assert warnings == []


def test_choose_to_columns_warns_when_no_email_columns() -> None:
    sheet = SheetInfo(
        name="Employees",
        columns=[
            ColumnInfo(index=1, header="姓名", key="姓名", required=True),
            ColumnInfo(index=2, header="部门", key="部门", required=False),
        ],
        header_row_index=1,
    )
    rows = [
        _make_row(2, {"姓名": "Ada", "部门": "Engineering"}),
        _make_row(3, {"姓名": "Grace", "部门": "HR"}),
        _make_row(4, {"姓名": "Alan", "部门": "Sales"}),
    ]

    selected, warnings = choose_to_columns(sheet, rows)

    assert [column.key for column in selected] == ["姓名", "部门"]
    assert warnings == [_WARNING_NO_EMAIL]
