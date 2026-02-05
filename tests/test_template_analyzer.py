"""Tests for template_analyzer module."""

from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from app.core.errors import TemplateValidationError
from app.core.template_analyzer import analyze_template

_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _document_xml(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_WORD_NAMESPACE}">' 
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )


def _write_docx(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    document_xml = _document_xml(body)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml.encode("utf-8"))
    return path


def test_token_extraction_from_minimal_docx(tmp_path: Path) -> None:
    body = (
        "<w:p>"
        "<w:r><w:t>«姓名»</w:t></w:r>"
        "<w:r><w:t>«年份»</w:t></w:r>"
        "<w:r><w:t>«部门»</w:t></w:r>"
        "</w:p>"
    )
    docx_path = _write_docx(tmp_path / "tokens.docx", body)

    info = analyze_template(docx_path)

    assert [field.key for field in info.fields] == ["姓名", "年份", "部门"]
    assert [field.source for field in info.fields] == ["token", "token", "token"]


def test_mergefield_extraction_from_instr_text(tmp_path: Path) -> None:
    body = (
        "<w:p>"
        "<w:r><w:instrText>MERGEFIELD 姓名</w:instrText></w:r>"
        "</w:p>"
    )
    docx_path = _write_docx(tmp_path / "mergefield.docx", body)

    info = analyze_template(docx_path)

    assert len(info.fields) == 1
    field = info.fields[0]
    assert field.key == "姓名"
    assert field.placeholder == "姓名"
    assert field.source == "mergefield"


def test_mergefield_preference_and_deduplication(tmp_path: Path) -> None:
    body = (
        "<w:p>"
        "<w:r><w:t>«姓 名»</w:t></w:r>"
        "<w:r><w:instrText>MERGEFIELD 姓名</w:instrText></w:r>"
        "</w:p>"
    )
    docx_path = _write_docx(tmp_path / "dedupe.docx", body)

    info = analyze_template(docx_path)

    assert len(info.fields) == 1
    field = info.fields[0]
    assert field.key == "姓名"
    assert field.placeholder == "姓名"
    assert field.source == "mergefield"


def test_template_validation_error_when_no_fields(tmp_path: Path) -> None:
    body = "<w:p><w:r><w:t>纯文本</w:t></w:r></w:p>"
    docx_path = _write_docx(tmp_path / "empty.docx", body)

    with pytest.raises(TemplateValidationError):
        analyze_template(docx_path)
