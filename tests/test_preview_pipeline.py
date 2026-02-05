"""Tests for preview pipeline helpers without UI dependencies."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.models import RowData, RowResult, TemplateInfo
from app.core.run_controller import RunConfig, RunController
from app.ui.preview_logic import apply_preview_result_to_viewer


class StubMerger:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, TemplateInfo, RowData]] = []

    def __call__(self, template_bytes: bytes, template_info: TemplateInfo, row: RowData) -> bytes:
        self.calls.append((template_bytes, template_info, row))
        return b"merged-bytes"


class StubRenderer:
    def __init__(self, html: str) -> None:
        self.html = html
        self.calls: list[bytes] = []

    def __call__(self, merged_bytes: bytes) -> str:
        self.calls.append(merged_bytes)
        return self.html


class GraphFactorySpy:
    def __init__(self) -> None:
        self.called = False

    def __call__(self, tenant_id: str, client_id: str, client_secret: str) -> object:
        self.called = True
        raise AssertionError("Graph client factory should not be called during preview.")


def _build_config() -> RunConfig:
    return RunConfig(
        template_path=Path("template.docx"),
        excel_path=Path("data.xlsx"),
        to_column_key="email",
        from_email="",
        tenant_id="",
        client_id="",
        client_secret="",
        subject_template="Hello {Name}",
        save_to_sent=True,
        dry_run=False,
    )


def _build_row() -> RowData:
    return RowData(
        row_index=1,
        values_by_key={
            "email": "user@example.com",
            "name": "Ada",
        },
    )


def test_preview_row_uses_dry_run_and_render_subject(monkeypatch: Any) -> None:
    merger = StubMerger()
    renderer = StubRenderer("<html>Preview</html>")
    graph_factory = GraphFactorySpy()

    controller = RunController(
        graph_client_factory=graph_factory,
        merger=merger,
        renderer=renderer,
    )

    render_calls: list[tuple[str, RowData]] = []

    def fake_render_subject(template: str, row: RowData) -> str:
        render_calls.append((template, row))
        return "Preview Subject"

    monkeypatch.setattr("app.core.run_controller.render_subject", fake_render_subject)

    config = _build_config()
    row = _build_row()
    template_info = TemplateInfo(template_name="template")

    result = controller.preview_row(
        config=config,
        row=row,
        template_info=template_info,
        template_bytes=b"template",
    )

    assert result.success is True
    assert result.rendered_body == "<html>Preview</html>"
    assert result.rendered_subject == "Preview Subject"
    assert render_calls == [("Hello {Name}", row)]
    assert graph_factory.called is False


def test_apply_preview_result_passes_html_to_viewer() -> None:
    row = _build_row()
    result = RowResult(
        row=row,
        success=True,
        rendered_subject="Subject",
        rendered_body="<p>HTML</p>",
    )

    subject_calls: list[str] = []
    html_calls: list[str] = []

    def set_subject(value: str) -> None:
        subject_calls.append(value)

    def set_html(value: str) -> None:
        html_calls.append(value)

    def empty_html(message: str) -> str:
        return f"<p>{message}</p>"

    apply_preview_result_to_viewer(
        result,
        set_subject=set_subject,
        set_html=set_html,
        empty_html=empty_html,
    )

    assert subject_calls == ["Subject"]
    assert html_calls == ["<p>HTML</p>"]
