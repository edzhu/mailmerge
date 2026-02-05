"""Template inspection utilities for mail-merge messages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, List, Optional, Sequence, TYPE_CHECKING
import zipfile

from app.core.canonicalize import canonicalize
from app.core.errors import OptionalDependencyError, TemplateValidationError
from app.core.models import FieldInfo, TemplateInfo

if TYPE_CHECKING:
    from lxml import etree

_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NSMAP = {"w": _WORD_NAMESPACE}
_MERGEFIELD_PATTERN = re.compile(r"MERGEFIELD\b", re.IGNORECASE)
_FORMAT_SWITCH_PATTERN = re.compile(
    r"\\#\s*(?:\"([^\"]+)\"|([^\s\\]+))",
    re.IGNORECASE,
)
_TOKEN_PATTERN = re.compile(r"«([^»]+)»")


@dataclass(frozen=True)
class _MergeField:
    name: str
    format_hint: Optional[str]


@dataclass(frozen=True)
class _FieldCandidate:
    key: str
    original_name: str
    source: str
    format_hint: Optional[str]


def analyze_template(path: Path) -> TemplateInfo:
    """Analyze a Word template and return the merge fields it defines."""
    template_path = Path(path)
    document_xml = _load_document_xml(template_path)
    root = _parse_document_xml(document_xml)
    candidates = _extract_candidates(root)
    fields = _merge_candidates(candidates)
    if not fields:
        raise TemplateValidationError("Template contains no merge fields")
    return TemplateInfo(template_name=template_path.name, fields=fields)


def _load_document_xml(path: Path) -> bytes:
    """Load the main document XML from a .docx archive."""
    try:
        with zipfile.ZipFile(path) as archive:
            try:
                return archive.read("word/document.xml")
            except KeyError as exc:
                raise TemplateValidationError(
                    "Template is missing word/document.xml."
                ) from exc
    except FileNotFoundError as exc:
        raise TemplateValidationError(f"Template not found: {path}") from exc
    except (zipfile.BadZipFile, OSError) as exc:
        raise TemplateValidationError("Template is not a valid .docx file.") from exc


def _parse_document_xml(document_xml: bytes) -> "etree._Element":
    """Parse document XML into an element tree."""
    etree = _load_lxml()
    try:
        return etree.fromstring(document_xml)
    except etree.XMLSyntaxError as exc:
        raise TemplateValidationError("Template document XML is invalid.") from exc


def _load_lxml() -> Any:
    """Load lxml and translate missing dependency errors."""
    try:
        from lxml import etree
    except ModuleNotFoundError as exc:
        raise OptionalDependencyError(
            "lxml is required to analyze Word templates."
        ) from exc
    return etree


def _extract_candidates(root: Any) -> List[_FieldCandidate]:
    """Extract merge field and token candidates from the document tree."""
    candidates: List[_FieldCandidate] = []
    for paragraph in root.xpath(".//w:p", namespaces=_NSMAP):
        candidates.extend(_extract_paragraph_candidates(paragraph))
    return candidates


def _extract_paragraph_candidates(paragraph: Any) -> List[_FieldCandidate]:
    events: List[_FieldCandidate] = []
    instr_texts: List[str] = []
    first_instr_position: Optional[int] = None

    for element in paragraph.iter():
        if element.tag == f"{{{_WORD_NAMESPACE}}}instrText":
            if first_instr_position is None:
                first_instr_position = len(events)
            text = element.text or ""
            instr_texts.append(text)
            for merge_field in _parse_mergefields(text):
                candidate = _candidate_from_mergefield(merge_field)
                if candidate:
                    events.append(candidate)
        elif element.tag == f"{{{_WORD_NAMESPACE}}}t":
            text = element.text or ""
            for token in _extract_tokens(text):
                candidate = _candidate_from_token(token)
                if candidate:
                    events.append(candidate)

    if instr_texts:
        joined_text = "".join(instr_texts)
        joined_candidates: List[_FieldCandidate] = []
        for merge_field in _parse_mergefields(joined_text):
            candidate = _candidate_from_mergefield(merge_field)
            if candidate:
                joined_candidates.append(candidate)
        if joined_candidates:
            existing_merge_keys = {
                candidate.key
                for candidate in events
                if candidate.source == "mergefield"
            }
            new_candidates = [
                candidate
                for candidate in joined_candidates
                if candidate.key not in existing_merge_keys
            ]
            if new_candidates:
                insert_at = (
                    first_instr_position
                    if first_instr_position is not None
                    else len(events)
                )
                events[insert_at:insert_at] = new_candidates

    return events


def _extract_tokens(text: str) -> List[str]:
    tokens: List[str] = []
    for match in _TOKEN_PATTERN.finditer(text):
        value = match.group(1).strip()
        if value:
            tokens.append(value)
    return tokens


def _parse_mergefields(text: str) -> List[_MergeField]:
    results: List[_MergeField] = []
    if not text:
        return results

    matches = list(_MERGEFIELD_PATTERN.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = text[match.end() : end]
        name, remainder = _extract_field_name(segment)
        if not name:
            continue
        format_hint = _extract_format_hint(remainder)
        results.append(_MergeField(name=name, format_hint=format_hint))
    return results


def _extract_field_name(segment: str) -> tuple[Optional[str], str]:
    remainder = segment.lstrip()
    if not remainder:
        return None, ""
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


def _candidate_from_mergefield(merge_field: _MergeField) -> Optional[_FieldCandidate]:
    return _build_candidate(
        merge_field.name,
        source="mergefield",
        format_hint=merge_field.format_hint,
    )


def _candidate_from_token(token: str) -> Optional[_FieldCandidate]:
    return _build_candidate(token, source="token", format_hint=None)


def _build_candidate(
    name: str,
    source: str,
    format_hint: Optional[str],
) -> Optional[_FieldCandidate]:
    cleaned = name.strip()
    if not cleaned:
        return None
    key = canonicalize(cleaned)
    if not key:
        return None
    return _FieldCandidate(
        key=key,
        original_name=cleaned,
        source=source,
        format_hint=format_hint,
    )


def _merge_candidates(candidates: Sequence[_FieldCandidate]) -> List[FieldInfo]:
    fields: List[FieldInfo] = []
    fields_by_key: dict[str, FieldInfo] = {}
    for candidate in candidates:
        existing = fields_by_key.get(candidate.key)
        if existing is None:
            field_info = FieldInfo(
                key=candidate.key,
                placeholder=candidate.original_name,
                label=None,
                required=True,
                source=candidate.source,
                format_hint=candidate.format_hint,
            )
            fields.append(field_info)
            fields_by_key[candidate.key] = field_info
            continue
        if candidate.source == "mergefield" and existing.source != "mergefield":
            existing.placeholder = candidate.original_name
            existing.source = candidate.source
        if candidate.format_hint and existing.format_hint is None:
            existing.format_hint = candidate.format_hint
    return fields
