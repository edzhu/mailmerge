"""Merge engine utilities for Word templates."""

from __future__ import annotations

from datetime import date, datetime
import io
import re
from typing import Any, Mapping, Optional, TYPE_CHECKING
import zipfile

from app.core.canonicalize import canonicalize
from app.core.errors import MergeError, OptionalDependencyError
from app.core.models import RowData, TemplateInfo

if TYPE_CHECKING:
    from lxml import etree

_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NSMAP = {"w": _WORD_NAMESPACE}
_TOKEN_PATTERN = re.compile(r"«([^»]+)»")


def format_value(value: object, format_hint: str | None = None) -> str:
    """Format a value for document merging.

    Args:
        value: The value to format.
        format_hint: Optional numeric format hint.

    Returns:
        The formatted value as a string.
    """

    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        return value.rstrip()
    if isinstance(value, int):
        return _format_number(value, format_hint)
    if isinstance(value, float):
        return _format_number(value, format_hint)
    return str(value)


def merge_docx_bytes(
    template_docx_bytes: bytes,
    template: TemplateInfo,
    row: RowData,
) -> bytes:
    """Merge a row of data into a DOCX template provided as bytes."""

    replacements = _build_replacement_map(template, row)
    try:
        with zipfile.ZipFile(io.BytesIO(template_docx_bytes)) as archive:
            document_xml = _load_document_xml(archive)
            etree = _load_lxml()
            root = _parse_document_xml(document_xml, etree)
            if replacements:
                _replace_tokens(root, replacements)
                updated_document_xml = _serialize_document_xml(root, etree)
                return _write_updated_archive(
                    archive,
                    updated_document_xml,
                )
            return template_docx_bytes
    except zipfile.BadZipFile as exc:
        raise MergeError("Template is not a valid .docx file.") from exc
    except OSError as exc:
        raise MergeError("Unable to read .docx data.") from exc


def _format_number(value: float | int, format_hint: Optional[str]) -> str:
    if format_hint == "0.00":
        return f"{float(value):.2f}"
    if format_hint == "0":
        if isinstance(value, float):
            return f"{value:.0f}"
        return str(int(value))
    if isinstance(value, int):
        return str(int(value))
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}"


def _build_replacement_map(
    template: TemplateInfo,
    row: RowData,
) -> dict[str, str]:
    replacements: dict[str, str] = {}
    row_values = _canonical_row_values(row)
    for field in template.fields:
        key = canonicalize(field.key)
        if not key:
            continue
        if key not in row_values:
            continue
        formatted_value = format_value(row_values[key], field.format_hint)
        replacements[key] = formatted_value
        placeholder = _normalize_placeholder(field.placeholder)
        if placeholder:
            replacements[placeholder] = formatted_value
    return replacements


def _canonical_row_values(row: RowData) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in row.values_by_key.items():
        canonical_key = canonicalize(key)
        if canonical_key:
            values[canonical_key] = value
    return values


def _normalize_placeholder(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if "«" in cleaned or "»" in cleaned:
        cleaned = cleaned.replace("«", "").replace("»", "")
    return cleaned


def _load_document_xml(archive: zipfile.ZipFile) -> bytes:
    try:
        return archive.read("word/document.xml")
    except KeyError as exc:
        raise MergeError("Template is missing word/document.xml.") from exc


def _load_lxml() -> Any:
    try:
        from lxml import etree
    except ModuleNotFoundError as exc:
        raise OptionalDependencyError(
            "lxml is required to merge Word templates."
        ) from exc
    return etree


def _parse_document_xml(
    document_xml: bytes,
    etree: Any,
) -> "etree._Element":
    try:
        return etree.fromstring(document_xml)
    except etree.XMLSyntaxError as exc:
        raise MergeError("Template document XML is invalid.") from exc


def _serialize_document_xml(root: Any, etree: Any) -> bytes:
    try:
        return etree.tostring(
            root,
            encoding="UTF-8",
            xml_declaration=True,
        )
    except (TypeError, ValueError) as exc:
        raise MergeError("Unable to serialize merged document XML.") from exc


def _replace_tokens(root: Any, replacements: Mapping[str, str]) -> None:
    for paragraph in root.xpath(".//w:p", namespaces=_NSMAP):
        _replace_tokens_in_paragraph(paragraph, replacements)


def _replace_tokens_in_paragraph(
    paragraph: Any,
    replacements: Mapping[str, str],
) -> None:
    text_nodes = paragraph.xpath(".//w:t", namespaces=_NSMAP)
    if not text_nodes:
        return

    for node in text_nodes:
        text = node.text or ""
        replaced = _replace_text_tokens(text, replacements)
        if replaced != text:
            node.text = replaced

    joined_text = "".join(node.text or "" for node in text_nodes)
    replaced_joined = _replace_text_tokens(joined_text, replacements)
    if replaced_joined != joined_text:
        text_nodes[0].text = replaced_joined
        for node in text_nodes[1:]:
            node.text = ""


def _replace_text_tokens(text: str, replacements: Mapping[str, str]) -> str:
    if not text or "«" not in text:
        return text

    def _replacement(match: re.Match[str]) -> str:
        raw_token = match.group(1)
        token = raw_token.strip()
        if token in replacements:
            return replacements[token]
        canonical_token = canonicalize(token)
        if canonical_token in replacements:
            return replacements[canonical_token]
        return match.group(0)

    return _TOKEN_PATTERN.sub(_replacement, text)


def _write_updated_archive(
    archive: zipfile.ZipFile,
    updated_document_xml: bytes,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as new_archive:
        for info in archive.infolist():
            if info.filename == "word/document.xml":
                new_archive.writestr(info, updated_document_xml)
            else:
                new_archive.writestr(info, archive.read(info.filename))
    return output.getvalue()
