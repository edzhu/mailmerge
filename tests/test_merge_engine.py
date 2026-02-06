"""Tests for merge_engine module."""

from __future__ import annotations

from datetime import datetime, timezone
import io
import zipfile

import pytest

from mailmerge.core.merge_engine import format_value, merge_docx_bytes
from mailmerge.core.models import FieldInfo, RowData, TemplateInfo

_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _document_xml(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_WORD_NAMESPACE}">' 
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )


def _docx_bytes(body: str) -> bytes:
    document_xml = _document_xml(body).encode("utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    return output.getvalue()


def _read_document_xml(docx_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as archive:
        return archive.read("word/document.xml").decode("utf-8")


def _build_template(field_keys: list[str]) -> TemplateInfo:
    return TemplateInfo(
        template_name="test-template",
        fields=[
            FieldInfo(key=key, placeholder=f"«{key}»")
            for key in field_keys
        ],
    )


def _require_lxml() -> None:
    pytest.importorskip("lxml")


def _extract_document_text(document_xml: str) -> str:
    _require_lxml()
    from lxml import etree

    root = etree.fromstring(document_xml.encode("utf-8"))
    text_nodes = root.xpath(".//w:t", namespaces={"w": _WORD_NAMESPACE})
    return "".join(node.text or "" for node in text_nodes)


@pytest.mark.parametrize(
    ("value", "format_hint", "expected"),
    [
        (None, None, ""),
        (42, None, "42"),
        (7.0, None, "7"),
        (12.5, "0.00", "12.50"),
        (datetime(2024, 1, 2, 15, 4, tzinfo=timezone.utc), None, "2024-01-02"),
    ],
    ids=[
        "none",
        "int",
        "float-integer-like",
        "float-hint",
        "datetime",
    ],
)
def test_format_value_rules(
    value: object,
    format_hint: str | None,
    expected: str,
) -> None:
    assert format_value(value, format_hint) == expected


def test_merge_docx_replaces_tokens() -> None:
    _require_lxml()
    body = (
        "<w:p>"
        "<w:r><w:t>«姓名»</w:t></w:r>"
        "<w:r><w:t> - </w:t></w:r>"
        "<w:r><w:t>«部门»</w:t></w:r>"
        "</w:p>"
    )
    docx_bytes = _docx_bytes(body)
    template = _build_template(["姓名", "部门"])
    row = RowData(row_index=1, values_by_key={"姓名": "Ada Lovelace", "部门": "工程"})

    merged_bytes = merge_docx_bytes(docx_bytes, template, row)
    merged_xml = _read_document_xml(merged_bytes)

    assert "Ada Lovelace" in merged_xml
    assert "工程" in merged_xml
    assert "«姓名»" not in merged_xml
    assert "«部门»" not in merged_xml


def test_merge_docx_handles_split_token_runs() -> None:
    _require_lxml()
    body = (
        "<w:p>"
        "<w:r><w:t>«姓</w:t></w:r>"
        "<w:r><w:t>名»</w:t></w:r>"
        "</w:p>"
    )
    docx_bytes = _docx_bytes(body)
    template = _build_template(["姓名"])
    row = RowData(row_index=1, values_by_key={"姓名": "Grace Hopper"})

    merged_bytes = merge_docx_bytes(docx_bytes, template, row)
    merged_xml = _read_document_xml(merged_bytes)

    assert "Grace Hopper" in merged_xml
    assert "«" not in merged_xml
    assert "»" not in merged_xml


def test_merge_docx_replaces_mergefield_results_without_tokens() -> None:
    _require_lxml()
    body = (
        "<w:p>"
        "<w:r><w:t>Hello </w:t></w:r>"
        "<w:r><w:fldChar w:fldCharType=\"begin\"/></w:r>"
        "<w:r><w:instrText xml:space=\"preserve\"> MERGEFIELD Name </w:instrText></w:r>"
        "<w:r><w:fldChar w:fldCharType=\"separate\"/></w:r>"
        "<w:r><w:t>Old</w:t></w:r>"
        "<w:r><w:t>Value</w:t></w:r>"
        "<w:r><w:fldChar w:fldCharType=\"end\"/></w:r>"
        "<w:r><w:t>!</w:t></w:r>"
        "</w:p>"
    )
    docx_bytes = _docx_bytes(body)
    template = _build_template(["Name"])
    row = RowData(row_index=1, values_by_key={"Name": "Ada Lovelace"})

    merged_bytes = merge_docx_bytes(docx_bytes, template, row)
    merged_xml = _read_document_xml(merged_bytes)

    assert _extract_document_text(merged_xml) == "Hello Ada Lovelace!"
