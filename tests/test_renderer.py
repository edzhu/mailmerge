"""Tests for html_renderer module."""

from __future__ import annotations

from html import escape as html_escape
import io
import zipfile
from xml.sax.saxutils import escape as xml_escape

from app.core.html_renderer import docx_bytes_to_html

_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _document_xml(text: str) -> str:
    escaped = xml_escape(text)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_WORD_NAMESPACE}">' 
        "<w:body>"
        "<w:p>"
        "<w:r>"
        f"<w:t>{escaped}</w:t>"
        "</w:r>"
        "</w:p>"
        "</w:body>"
        "</w:document>"
    )


def _docx_bytes(text: str) -> bytes:
    document_xml = _document_xml(text).encode("utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    return output.getvalue()


def test_docx_bytes_to_html_contains_text_and_charset() -> None:
    text = "你好，世界"
    html = docx_bytes_to_html(_docx_bytes(text))

    assert isinstance(html, str)
    assert html.strip()
    assert 'charset="utf-8"' in html.lower()
    escaped = html_escape(text)
    assert text in html or escaped in html
