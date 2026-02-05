"""Tests for excel_loader module."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import ExcelValidationError
from app.core.excel_loader import load_matching_sheet
from app.core.models import FieldInfo, TemplateInfo

openpyxl = pytest.importorskip("openpyxl")


def _build_template() -> TemplateInfo:
    return TemplateInfo(
        template_name="test-template",
        fields=[
            FieldInfo(key="Full Name", placeholder="Full Name", required=True),
            FieldInfo(key="Email Address", placeholder="Email Address", required=True),
        ],
    )


def _write_workbook_with_match(path: Path) -> Path:
    workbook = openpyxl.Workbook()
    missing_sheet = workbook.active
    missing_sheet.title = "Missing Fields"
    missing_sheet.append(["Full Name", "Department"])

    data_sheet = workbook.create_sheet("Mail Merge Data")
    data_sheet.cell(row=3, column=1, value="Full Name")
    data_sheet.cell(row=3, column=2, value="Email Address")
    data_sheet.cell(row=4, column=1, value="Ada Lovelace")
    data_sheet.cell(row=4, column=2, value="ada@example.com")
    data_sheet.cell(row=5, column=1, value=" ")
    data_sheet.cell(row=5, column=2, value="")

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    workbook.close()
    return path


def _write_workbook_without_match(path: Path) -> Path:
    workbook = openpyxl.Workbook()
    only_name = workbook.active
    only_name.title = "Only Name"
    only_name.append(["Full Name", "Department"])

    only_email = workbook.create_sheet("Only Email")
    only_email.append(["Email Address", "Department"])

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    workbook.close()
    return path


def test_load_matching_sheet_selects_sheet_and_rows(tmp_path: Path) -> None:
    template = _build_template()
    excel_path = _write_workbook_with_match(tmp_path / "data.xlsx")

    sheet_info, rows = load_matching_sheet(excel_path, template)

    assert sheet_info.name == "Mail Merge Data"
    assert sheet_info.header_row_index == 3
    assert {column.key for column in sheet_info.columns} == {
        "FullName",
        "EmailAddress",
    }

    assert len(rows) == 1
    row = rows[0]
    assert row.row_index == 4
    assert row.values_by_key["FullName"] == "Ada Lovelace"
    assert row.values_by_key["EmailAddress"] == "ada@example.com"
    assert "Full Name" not in row.values_by_key


def test_load_matching_sheet_raises_when_no_match(tmp_path: Path) -> None:
    template = _build_template()
    excel_path = _write_workbook_without_match(tmp_path / "missing.xlsx")

    with pytest.raises(ExcelValidationError):
        load_matching_sheet(excel_path, template)
