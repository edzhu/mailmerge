"""Validation helpers for the mail-merge emailer."""

from __future__ import annotations

import re

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(value: str) -> bool:
    """Return True when the value looks like an email address."""
    candidate = value.strip()
    if not candidate:
        return False
    return _EMAIL_PATTERN.fullmatch(candidate) is not None


__all__ = ["is_valid_email"]
