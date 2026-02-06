"""Canonicalization utilities for mail-merge inputs."""

from __future__ import annotations

import unicodedata

_REMOVE_CHARS = " \u3000_/\\:：-—"
_REMOVE_TRANSLATION = str.maketrans("", "", _REMOVE_CHARS)


def canonicalize(value: object) -> str:
    """Return a Chinese-friendly canonical form of the input.

    The value is normalized with Unicode NFKC, stripped of leading/trailing
    whitespace, has any guillemets (« ») removed, and then deletes spaces
    (ASCII and full-width) along with underscores, slashes, colons (ASCII and
    full-width), hyphens, and em dashes. Non-string inputs are coerced with
    ``str()``; ``None`` is treated as an empty string.
    """

    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)

    normalized = unicodedata.normalize("NFKC", text).strip()
    if "«" in normalized or "»" in normalized:
        normalized = normalized.replace("«", "").replace("»", "")
    if not normalized:
        return ""

    return normalized.translate(_REMOVE_TRANSLATION)
