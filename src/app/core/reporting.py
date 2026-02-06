"""Result reporting utilities for the mail-merge emailer."""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Mapping, Sequence

from app.core.canonicalize import canonicalize
from app.core.errors import MailMergeError
from app.core.models import CellValue, RowData, RowResult, RunSummary
from app.core.validation import is_valid_email

_DEFAULT_RESULTS_FILENAME = "results.csv"
_IDENTIFIER_LABELS = ("序号", "姓名")
_IDENTIFIER_KEYS = {label: canonicalize(label) for label in _IDENTIFIER_LABELS}
_EMAIL_LABELS = (
    "email",
    "e-mail",
    "mail",
    "to",
    "recipient",
    "邮箱",
    "电子邮箱",
    "电子邮件",
    "收件人",
    "收件邮箱",
)
_SUBJECT_FIELDS = ("rendered_subject", "subject")


def write_results_csv(run_dir: Path, summary: RunSummary) -> Path:
    """Write a deterministic results.csv file into the run directory."""
    run_path = _normalize_run_path(run_dir)
    results = _extract_results(summary)
    include_subject = _supports_subject(results)
    headers = _build_headers(include_subject)

    try:
        run_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MailMergeError(
            f"Unable to create run directory: {run_path}"
        ) from exc

    csv_path = run_path / _DEFAULT_RESULTS_FILENAME
    try:
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(headers)
            for index, result in enumerate(results, start=1):
                writer.writerow(_build_row(result, index, include_subject))
    except OSError as exc:
        raise MailMergeError(f"Unable to write results CSV: {csv_path}") from exc

    return csv_path


def _normalize_run_path(run_dir: Path) -> Path:
    try:
        return Path(run_dir)
    except (TypeError, ValueError) as exc:
        raise MailMergeError("run_dir must be a valid path.") from exc


def _extract_results(summary: RunSummary) -> list[RowResult]:
    results = _get_attr(summary, "results")
    if results is None:
        return []
    if isinstance(results, Sequence) and not isinstance(results, (str, bytes)):
        return list(results)
    try:
        return list(results)
    except TypeError:
        return []


def _supports_subject(results: Sequence[RowResult]) -> bool:
    if any(_has_subject_fields(result) for result in results):
        return True
    return _has_subject_fields(RowResult)


def _has_subject_fields(obj: object) -> bool:
    if isinstance(obj, Mapping):
        return any(field in obj for field in _SUBJECT_FIELDS)
    return any(hasattr(obj, field) for field in _SUBJECT_FIELDS)


def _build_headers(include_subject: bool) -> list[str]:
    headers = [
        "row_index",
        "to_email",
        "status",
        "error",
        "identifier_序号",
        "identifier_姓名",
    ]
    if include_subject:
        headers.append("subject")
    return headers


def _build_row(result: RowResult, default_index: int, include_subject: bool) -> list[str]:
    row = _get_attr(result, "row")
    values_by_key = _get_values_by_key(row)
    row_index_value = _get_attr(row, "row_index")
    if row_index_value is None:
        row_index_value = _get_attr(result, "row_index")
    row_index = _stringify_value(row_index_value)
    if not row_index:
        row_index = str(default_index)

    record = [
        row_index,
        _resolve_to_email(values_by_key),
        _resolve_status(result),
        _stringify_value(_get_attr(result, "error")),
        _resolve_identifier(values_by_key, _IDENTIFIER_KEYS.get("序号", "")),
        _resolve_identifier(values_by_key, _IDENTIFIER_KEYS.get("姓名", "")),
    ]
    if include_subject:
        record.append(_resolve_subject(result))
    return record


def _get_values_by_key(row: RowData | None) -> Mapping[str, CellValue]:
    values = _get_attr(row, "values_by_key")
    if isinstance(values, Mapping):
        return values
    return {}


def _resolve_identifier(values_by_key: Mapping[str, CellValue], key: str) -> str:
    if not values_by_key or not key:
        return ""
    return _stringify_value(values_by_key.get(key))


def _resolve_to_email(values_by_key: Mapping[str, CellValue]) -> str:
    if not values_by_key:
        return ""
    for key in _email_keys():
        if key in values_by_key:
            candidate = _stringify_value(values_by_key.get(key))
            if candidate:
                return candidate
    for value in values_by_key.values():
        candidate = _stringify_value(value)
        if candidate and is_valid_email(candidate):
            return candidate
    return ""


def _resolve_status(result: RowResult) -> str:
    status = _stringify_value(_get_attr(result, "status"))
    if status:
        return status
    success = _get_attr(result, "success")
    if isinstance(success, bool):
        return "success" if success else "failure"
    return "unknown"


def _resolve_subject(result: RowResult) -> str:
    value = _get_attr(result, "rendered_subject")
    if value is None:
        value = _get_attr(result, "subject")
    return _stringify_value(value)


def _stringify_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _get_attr(obj: object, name: str) -> object | None:
    if obj is None:
        return None
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, Mapping):
        return obj.get(name)
    return None


def _email_keys() -> tuple[str, ...]:
    keys: list[str] = []
    for label in _EMAIL_LABELS:
        key = canonicalize(label)
        if key and key not in keys:
            keys.append(key)
    return tuple(keys)
