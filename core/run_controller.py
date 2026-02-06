"""Compatibility wrapper for run controller orchestration."""

from __future__ import annotations

from mailmerge.core.run_controller import (
    GraphClientProtocol,
    ProgressEvent,
    RunConfig,
    RunController,
    RunSummary,
    RowResult,
)

__all__ = [
    "GraphClientProtocol",
    "ProgressEvent",
    "RunConfig",
    "RunController",
    "RunSummary",
    "RowResult",
]
