"""UI helper logic for configuration and controller wiring."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import threading

from app.core import validation
from app.core.run_controller import ProgressEvent, RunConfig, RunController, RunSummary


def is_from_email_valid(value: str) -> bool:
    """Return True when the from-email value passes validation gating."""
    return validation.is_valid_email(value)


def build_run_config_from_inputs(
    *,
    template_path: str,
    excel_path: str,
    to_column_key: str,
    from_email: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    subject_template: str,
    save_to_sent: bool = True,
    dry_run: bool = False,
) -> RunConfig:
    """Build a RunConfig from UI-sourced values.

    Whitespace is stripped from text inputs before constructing the config.
    """
    return RunConfig(
        template_path=Path(template_path.strip()),
        excel_path=Path(excel_path.strip()),
        to_column_key=to_column_key.strip(),
        from_email=from_email.strip(),
        tenant_id=tenant_id.strip(),
        client_id=client_id.strip(),
        client_secret=client_secret.strip(),
        subject_template=subject_template.strip(),
        save_to_sent=save_to_sent,
        dry_run=dry_run,
    )


def run_controller_with_cancel(
    *,
    controller: RunController,
    config: RunConfig,
    on_progress: Callable[[ProgressEvent], None] | None,
    cancel_token: threading.Event | None,
    run_dir: Path | None = None,
) -> RunSummary:
    """Execute the controller while preserving the cancel-token wiring."""
    return controller.run(
        config,
        on_progress=on_progress,
        cancel_token=cancel_token,
        run_dir=run_dir,
    )
