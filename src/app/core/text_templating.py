"""Subject template rendering utilities."""

from __future__ import annotations

import re
from collections.abc import Mapping

from app.core.canonicalize import canonicalize
from app.core.merge_engine import format_value
from app.core.models import RowData

_TOKEN_PATTERN = re.compile(r"\{([^{}]+)\}")


def render_subject(template: str, row: RowData) -> str:
    """Render a subject template, replacing unknown tokens with empty strings."""

    if not template:
        return ""

    replacements = _build_replacements(row)
    rendered = _TOKEN_PATTERN.sub(
        lambda match: _replace_token(match, replacements),
        template,
    )
    return rendered.strip()


def _build_replacements(row: RowData) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for key, value in row.values_by_key.items():
        canonical_key = canonicalize(key)
        if not canonical_key:
            continue
        replacements[canonical_key] = format_value(value)
    return replacements


def _replace_token(match: re.Match[str], replacements: Mapping[str, str]) -> str:
    token = match.group(1).strip()
    if not token:
        return ""
    if token in replacements:
        return replacements[token]
    canonical_token = canonicalize(token)
    if canonical_token and canonical_token in replacements:
        return replacements[canonical_token]
    return ""
