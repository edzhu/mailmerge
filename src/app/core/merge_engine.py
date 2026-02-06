"""Merge engine utilities for Word templates."""

from __future__ import annotations

from dataclasses import dataclass, field
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
_MERGEFIELD_PATTERN = re.compile(r"MERGEFIELD\b", re.IGNORECASE)
_FORMAT_SWITCH_PATTERN = re.compile(
    r"\\#\s*(?:\"([^\"]+)\"|([^\s\\]+))",
    re.IGNORECASE,
)
_FIELD_CHAR_TAG = f"{{{_WORD_NAMESPACE}}}fldChar"
_FIELD_CHAR_TYPE_ATTR = f"{{{_WORD_NAMESPACE}}}fldCharType"
_INSTR_TEXT_TAG = f"{{{_WORD_NAMESPACE}}}instrText"
_TEXT_TAG = f"{{{_WORD_NAMESPACE}}}t"


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

    row_values = _canonical_row_values(row)
    replacements = _build_replacement_map(template, row, row_values=row_values)
    try:
        with zipfile.ZipFile(io.BytesIO(template_docx_bytes)) as archive:
            document_xml = _load_document_xml(archive)
            etree = _load_lxml()
            root = _parse_document_xml(document_xml, etree)
            if replacements:
                _replace_tokens(root, replacements)
                _replace_mergefields(root, replacements, row_values, template)
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
    row_values: Optional[Mapping[str, object]] = None,
) -> dict[str, str]:
    replacements: dict[str, str] = {}
    if row_values is None:
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


@dataclass
class _FieldContext:
    instr_text_parts: list[str] = field(default_factory=list)
    mergefield_name: Optional[str] = None
    format_hint: Optional[str] = None
    in_result: bool = False
    is_mergefield: bool = False
    result_nodes: list[Any] = field(default_factory=list)
    replacement_value: Optional[str] = None


def _replace_mergefields(
    root: Any,
    replacements: Mapping[str, str],
    row_values: Mapping[str, object],
    template: TemplateInfo,
) -> None:
    format_hints = _build_format_hint_map(template)
    for paragraph in root.xpath(".//w:p", namespaces=_NSMAP):
        _replace_mergefields_in_paragraph(
            paragraph,
            replacements,
            row_values,
            format_hints,
        )


def _build_format_hint_map(template: TemplateInfo) -> dict[str, str]:
    format_hints: dict[str, str] = {}
    for field in template.fields:
        key = canonicalize(field.key)
        if not key:
            continue
        if field.format_hint:
            format_hints[key] = field.format_hint
    return format_hints


def _replace_mergefields_in_paragraph(
    paragraph: Any,
    replacements: Mapping[str, str],
    row_values: Mapping[str, object],
    format_hints: Mapping[str, str],
) -> None:
    contexts: list[_FieldContext] = []

    for element in paragraph.iter():
        if element.tag == _FIELD_CHAR_TAG:
            field_type = element.get(_FIELD_CHAR_TYPE_ATTR)
            if field_type == "begin":
                contexts.append(_FieldContext())
            elif field_type == "separate":
                if not contexts:
                    continue
                context = contexts[-1]
                if context.in_result:
                    continue
                instr_text = "".join(context.instr_text_parts)
                field_name, format_hint = _parse_mergefield_instruction(instr_text)
                if field_name is not None and field_name.strip():
                    context.is_mergefield = True
                    context.mergefield_name = field_name
                    context.format_hint = format_hint
                    context.replacement_value = _resolve_mergefield_value(
                        field_name,
                        format_hint,
                        row_values,
                        replacements,
                        format_hints,
                    )
                context.in_result = True
            elif field_type == "end":
                if not contexts:
                    continue
                context = contexts.pop()
                _apply_mergefield_replacement(context)
        elif element.tag == _INSTR_TEXT_TAG:
            if not contexts:
                continue
            context = contexts[-1]
            if context.in_result:
                continue
            context.instr_text_parts.append(element.text or "")
        elif element.tag == _TEXT_TAG:
            if not contexts:
                continue
            context = contexts[-1]
            if context.in_result:
                if context.is_mergefield:
                    context.result_nodes.append(element)
                continue
            context.instr_text_parts.append(element.text or "")

    while contexts:
        context = contexts.pop()
        _apply_mergefield_replacement(context)


def _apply_mergefield_replacement(context: _FieldContext) -> None:
    if not context.is_mergefield:
        return
    if context.replacement_value is None:
        return
    if not context.result_nodes:
        return
    context.result_nodes[0].text = context.replacement_value
    for node in context.result_nodes[1:]:
        node.text = ""


def _parse_mergefield_instruction(text: str) -> tuple[Optional[str], Optional[str]]:
    if not text:
        return None, None
    match = _MERGEFIELD_PATTERN.search(text)
    if not match:
        return None, None
    segment = text[match.end() :]
    field_name, remainder = _extract_field_name(segment)
    if field_name is None:
        return None, None
    format_hint = _extract_format_hint(remainder)
    return field_name, format_hint


def _extract_field_name(segment: str) -> tuple[Optional[str], str]:
    remainder = segment.lstrip()
    if not remainder:
        return "", ""
    if remainder[0] == '"':
        closing = remainder.find('"', 1)
        if closing == -1:
            return None, ""
        name = remainder[1:closing].strip()
        return name, remainder[closing + 1 :]
    if remainder[0] == "'":
        closing = remainder.find("'", 1)
        if closing == -1:
            return None, ""
        name = remainder[1:closing].strip()
        return name, remainder[closing + 1 :]
    match = re.match(r"([^\s\\]+)", remainder)
    if not match:
        return None, ""
    name = match.group(1).strip()
    return name, remainder[match.end() :]


def _extract_format_hint(remainder: str) -> Optional[str]:
    match = _FORMAT_SWITCH_PATTERN.search(remainder)
    if not match:
        return None
    value = match.group(1) or match.group(2) or ""
    value = value.strip()
    return value or None


def _resolve_mergefield_value(
    field_name: str,
    format_hint: Optional[str],
    row_values: Mapping[str, object],
    replacements: Mapping[str, str],
    format_hints: Mapping[str, str],
) -> Optional[str]:
    canonical_name = canonicalize(field_name)
    if canonical_name:
        if canonical_name in row_values:
            value = row_values[canonical_name]
            effective_hint = format_hint or format_hints.get(canonical_name)
            return format_value(value, effective_hint)
        if canonical_name in replacements:
            return replacements[canonical_name]
    placeholder = _normalize_placeholder(field_name)
    if placeholder and placeholder in replacements:
        return replacements[placeholder]
    return None


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
