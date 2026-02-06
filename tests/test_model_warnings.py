"""Tests for warnings defaults on core models."""

from __future__ import annotations

from app.core.models import SheetInfo, TemplateInfo


def test_template_info_warnings_default_is_empty_list() -> None:
    template_info = TemplateInfo(template_name="template.docx")
    assert isinstance(template_info.warnings, list)
    assert template_info.warnings == []

    other_template = TemplateInfo(template_name="other.docx")
    assert template_info.warnings is not other_template.warnings

    template_info.warnings.append("missing field")
    assert template_info.warnings == ["missing field"]
    assert other_template.warnings == []


def test_sheet_info_warnings_default_is_empty_list() -> None:
    sheet_info = SheetInfo(name="Contacts")
    assert isinstance(sheet_info.warnings, list)
    assert sheet_info.warnings == []

    other_sheet = SheetInfo(name="Leads")
    assert sheet_info.warnings is not other_sheet.warnings

    sheet_info.warnings.append("missing header")
    assert sheet_info.warnings == ["missing header"]
    assert other_sheet.warnings == []
