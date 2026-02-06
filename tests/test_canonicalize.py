"""Tests for canonicalize module."""

from __future__ import annotations

import pytest

from mailmerge.core.canonicalize import canonicalize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("事假/未到职", "事假未到职"),
        ("年假/其他", "年假其他"),
        ("备  注", "备注"),
        ("备__注", "备注"),
        ("«姓名»", "姓名"),
    ],
    ids=[
        "remove-slash-one",
        "remove-slash-two",
        "collapse-spaces",
        "remove-underscores",
        "strip-guillemets",
    ],
)
def test_canonicalize_removes_separators(raw: str, expected: str) -> None:
    assert canonicalize(raw) == expected
