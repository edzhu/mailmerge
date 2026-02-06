"""Tests for subject template rendering."""

from __future__ import annotations

from mailmerge.core.models import RowData
from mailmerge.core.text_templating import render_subject


def _make_row() -> RowData:
    return RowData(
        row_index=1,
        values_by_key={
            "年份": "2025",
            "月份": "02",
            "姓名": "Ada Lovelace",
        },
    )


def test_render_subject_replaces_basic_chinese_fields() -> None:
    row = _make_row()

    rendered = render_subject("{年份}{月份}{姓名}", row)

    assert rendered == "202502Ada Lovelace"


def test_render_subject_mixed_literals_and_fields() -> None:
    row = _make_row()

    rendered = render_subject("{年份}年{月份}月 - {姓名}", row)

    assert rendered == "2025年02月 - Ada Lovelace"


def test_render_subject_unknown_token_renders_empty() -> None:
    row = _make_row()

    rendered = render_subject("{不存在} - {姓名}", row)

    assert rendered == "- Ada Lovelace"


def test_render_subject_strips_leading_and_trailing_whitespace() -> None:
    row = _make_row()

    rendered = render_subject("  {姓名}  ", row)

    assert rendered == "Ada Lovelace"
