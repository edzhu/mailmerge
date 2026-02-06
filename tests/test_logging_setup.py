"""Tests for logging setup and audit writer behavior."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re

from mailmerge.core.logging_setup import AuditWriter, configure_logging, create_run_directory


_RUN_DIR_PATTERN = re.compile(r"^\d{8}-\d{6}(?:-\d{2})?$")


def _restore_logger(
    logger: logging.Logger,
    handlers: list[logging.Handler],
    level: int,
    propagate: bool,
) -> None:
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    for handler in handlers:
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = propagate


def test_create_run_directory_creates_timestamped_dir(tmp_path: Path) -> None:
    run_dir = create_run_directory(tmp_path)

    assert run_dir.exists()
    assert run_dir.is_dir()
    assert run_dir.parent == tmp_path
    assert _RUN_DIR_PATTERN.match(run_dir.name)


def test_configure_logging_writes_log_file(tmp_path: Path) -> None:
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    original_propagate = root_logger.propagate

    try:
        logger = configure_logging(tmp_path)
        logger.info("Hello from logging setup test.")

        for handler in logger.handlers:
            handler.flush()

        log_path = tmp_path / "run.log"
        assert log_path.exists()

        contents = log_path.read_text(encoding="utf-8")
        assert "Hello from logging setup test." in contents
    finally:
        _restore_logger(
            root_logger,
            original_handlers,
            original_level,
            original_propagate,
        )


def test_configure_logging_redacts_secrets(tmp_path: Path) -> None:
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    original_propagate = root_logger.propagate

    try:
        logger = configure_logging(tmp_path)
        config = {
            "tenant_id": "tenant",
            "client_secret": "super-secret",
            "nested": {"client_secret": "nested-secret"},
        }

        logger.info("Config: %s", config)
        for handler in logger.handlers:
            handler.flush()

        log_text = (tmp_path / "run.log").read_text(encoding="utf-8")
        assert "super-secret" not in log_text
        assert "nested-secret" not in log_text
        assert "client_secret" in log_text
        assert "***" in log_text
    finally:
        _restore_logger(
            root_logger,
            original_handlers,
            original_level,
            original_propagate,
        )


def test_audit_writer_writes_jsonl_and_redacts_secrets(tmp_path: Path) -> None:
    fixed_time = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    writer = AuditWriter(tmp_path, clock=lambda: fixed_time)

    writer.write_row_event(
        {
            "row_index": 1,
            "recipient": "ada@example.com",
            "status": "success",
            "identifiers": {"Email": "ada@example.com"},
            "error": None,
            "client_secret": "super-secret",
            "config": {"client_secret": "nested-secret"},
        }
    )
    writer.write_row_event(
        {
            "row_index": 2,
            "recipient": "grace@example.com",
            "status": "failure",
            "identifiers": {"Email": "grace@example.com"},
            "error": "something happened",
        }
    )

    audit_path = tmp_path / "audit.jsonl"
    lines = audit_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2

    rows = [json.loads(line) for line in lines]
    for row in rows:
        assert {
            "row_index",
            "recipient",
            "status",
            "identifiers",
            "error",
            "timestamp",
        }.issubset(row.keys())

    assert rows[0]["client_secret"] == "***"
    assert rows[0]["config"]["client_secret"] == "***"

    combined = json.dumps(rows)
    assert "super-secret" not in combined
    assert "nested-secret" not in combined
