"""Compatibility wrapper for logging setup utilities."""

from __future__ import annotations

from app.core.logging_setup import (
    AuditWriter,
    configure_logging,
    create_run_directory,
    sanitize_config,
)

__all__ = [
    "AuditWriter",
    "configure_logging",
    "create_run_directory",
    "sanitize_config",
]
