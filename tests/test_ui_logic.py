"""Tests for UI helper logic without Qt dependencies."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Any

from mailmerge.core.canonicalize import canonicalize
from mailmerge.core.run_controller import RunConfig
from mailmerge.ui.run_logic import (
    build_run_config_from_inputs,
    is_from_email_valid,
    run_controller_with_cancel,
)


def test_from_email_validation_delegates_to_core(monkeypatch: Any) -> None:
    calls: list[str] = []

    def fake_is_valid_email(value: str) -> bool:
        calls.append(value)
        return True

    monkeypatch.setattr("mailmerge.core.validation.is_valid_email", fake_is_valid_email)

    assert is_from_email_valid(" user@example.com ") is True
    assert calls == [" user@example.com "]


def test_build_run_config_from_inputs_builds_expected_values(tmp_path: Path) -> None:
    template_path = tmp_path / "template.docx"
    excel_path = tmp_path / "data.xlsx"

    config = build_run_config_from_inputs(
        template_path=str(template_path),
        excel_path=str(excel_path),
        to_column_key=" Email ",
        from_email=" sender@example.com ",
        tenant_id=" tenant ",
        client_id=" client ",
        client_secret=" secret ",
        subject_template=" Hello {Name} ",
        save_to_sent=False,
        dry_run=True,
    )

    assert isinstance(config, RunConfig)
    assert config.template_path == template_path
    assert config.excel_path == excel_path
    assert config.to_column_key == canonicalize(" Email ")
    assert config.from_email == "sender@example.com"
    assert config.tenant_id == "tenant"
    assert config.client_id == "client"
    assert config.client_secret == "secret"
    assert config.subject_template == "Hello {Name}"
    assert config.save_to_sent is False
    assert config.dry_run is True


def test_run_controller_with_cancel_passes_token() -> None:
    cancel_token = threading.Event()
    config = build_run_config_from_inputs(
        template_path="/tmp/template.docx",
        excel_path="/tmp/data.xlsx",
        to_column_key="Email",
        from_email="sender@example.com",
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        subject_template="Subject",
        save_to_sent=True,
        dry_run=True,
    )

    class StubController:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def run(
            self,
            run_config: RunConfig,
            on_progress: object | None = None,
            cancel_token: object | None = None,
            run_dir: Path | None = None,
        ) -> str:
            self.calls.append(
                {
                    "config": run_config,
                    "on_progress": on_progress,
                    "cancel_token": cancel_token,
                    "run_dir": run_dir,
                }
            )
            return "summary"

    stub = StubController()

    def on_progress(_: object) -> None:
        return None

    run_dir = Path("run-dir")

    result = run_controller_with_cancel(
        controller=stub,
        config=config,
        on_progress=on_progress,
        cancel_token=cancel_token,
        run_dir=run_dir,
    )

    assert result == "summary"
    assert stub.calls == [
        {
            "config": config,
            "on_progress": on_progress,
            "cancel_token": cancel_token,
            "run_dir": run_dir,
        }
    ]
