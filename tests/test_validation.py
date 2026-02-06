"""Tests for validation module."""

from __future__ import annotations

import pytest

from mailmerge.core.validation import is_valid_email


VALID_EMAILS = [
    "ada@example.com",
    "grace+newsletter@example.com",
    "alan@research.example.co.uk",
    "  ada@example.com  ",
    "\tgrace@example.com",
    "alan@example.com\n",
]

INVALID_EMAILS = [
    "",
    "   ",
    "not-an-email",
    "ada.example.com",
    "@example.com",
    "ada@",
    "ada@example",
    "ada@.com",
    "ada@example.",
    "ada @example.com",
    "ada@ example.com",
]


@pytest.mark.parametrize("value", VALID_EMAILS)
def test_is_valid_email_accepts_valid_addresses(value: str) -> None:
    assert is_valid_email(value)


@pytest.mark.parametrize("value", INVALID_EMAILS)
def test_is_valid_email_rejects_invalid_addresses(value: str) -> None:
    assert not is_valid_email(value)
