"""Logging configuration utilities for the mail-merge emailer."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any

from mailmerge.core.errors import ConfigurationError

Clock = Callable[[], datetime]

_DEFAULT_RUNS_DIR = "MailMergeRuns"
_RUN_DIR_FORMAT = "%Y%m%d-%H%M%S"
_DEFAULT_LOG_FILENAME = "run.log"
_DEFAULT_AUDIT_FILENAME = "audit.jsonl"
_SECRET_KEYS = {"client_secret"}
_SECRET_TEXT_PATTERN = re.compile(
    r"(client_secret\\s*[:=]\\s*)(['\"]?)[^,'\"\\s]+\\2",
    re.IGNORECASE,
)


def create_run_directory(base_dir: Path | None) -> Path:
    """Create and return a timestamped run directory."""
    root = _resolve_base_dir(base_dir)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigurationError(
            f"Unable to create base run directory: {root}"
        ) from exc
    timestamp = _format_run_timestamp(_local_now())
    return _create_unique_run_dir(root, timestamp)


def configure_logging(run_dir: Path) -> logging.Logger:
    """Configure console and file logging for a run."""
    run_path = Path(run_dir)
    try:
        run_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigurationError(f"Unable to create run directory: {run_path}") from exc

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redaction_filter = _SecretRedactionFilter()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(redaction_filter)

    file_handler = logging.FileHandler(
        run_path / _DEFAULT_LOG_FILENAME,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction_filter)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def sanitize_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return a redacted copy of configuration data suitable for logging."""
    return _sanitize_mapping(config)


class AuditWriter:
    """Write row-level audit events to a JSONL file."""

    def __init__(
        self,
        run_dir: Path,
        *,
        filename: str = _DEFAULT_AUDIT_FILENAME,
        clock: Clock | None = None,
    ) -> None:
        self._run_dir = Path(run_dir)
        self._path = self._run_dir / filename
        self._clock: Clock = clock or (lambda: datetime.now(timezone.utc))
        try:
            self._run_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigurationError(
                f"Unable to create audit directory: {self._run_dir}"
            ) from exc

    def write_row_event(self, event: Mapping[str, Any]) -> None:
        """Write a single row audit event as JSON lines."""
        payload: dict[str, Any] = dict(event)
        if "timestamp" not in payload:
            payload["timestamp"] = _format_audit_timestamp(self._now())
        payload = _sanitize_mapping(payload)
        payload = _json_ready(payload)
        line = json.dumps(payload, ensure_ascii=False)
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")
        except OSError as exc:
            raise ConfigurationError(
                f"Failed to write audit event to {self._path}"
            ) from exc

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise ConfigurationError(
                "Audit writer clock must return a timezone-aware datetime."
            )
        return now


class _SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _sanitize_value(record.msg)
        if record.args:
            record.args = _sanitize_args(record.args)
        return True


def _resolve_base_dir(base_dir: Path | None) -> Path:
    if base_dir is None:
        return Path.home() / _DEFAULT_RUNS_DIR
    return Path(base_dir).expanduser()


def _local_now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _format_run_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ConfigurationError("Timestamp must be timezone-aware.")
    return value.strftime(_RUN_DIR_FORMAT)


def _format_audit_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ConfigurationError("Timestamp must be timezone-aware.")
    return value.isoformat(timespec="seconds")


def _create_unique_run_dir(root: Path, timestamp: str) -> Path:
    for index in range(1000):
        suffix = "" if index == 0 else f"-{index:02d}"
        candidate = root / f"{timestamp}{suffix}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        except OSError as exc:
            raise ConfigurationError(
                f"Unable to create run directory: {candidate}"
            ) from exc
        return candidate
    raise ConfigurationError("Unable to create a unique run directory.")


def _sanitize_args(args: Any) -> Any:
    if isinstance(args, Mapping):
        return _sanitize_mapping(args)
    if isinstance(args, tuple):
        return tuple(_sanitize_value(value) for value in args)
    if isinstance(args, list):
        return [_sanitize_value(value) for value in args]
    return args


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, tuple):
        return tuple(_sanitize_value(item) for item in value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


def _sanitize_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in mapping.items():
        if _is_secret_key(str(key)):
            sanitized[str(key)] = "***"
        else:
            sanitized[str(key)] = _sanitize_value(value)
    return sanitized


def _is_secret_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized in _SECRET_KEYS


def _sanitize_text(text: str) -> str:
    return _SECRET_TEXT_PATTERN.sub(r"\1***", text)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


__all__ = ["AuditWriter", "configure_logging", "create_run_directory", "sanitize_config"]
