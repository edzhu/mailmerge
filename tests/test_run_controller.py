"""Tests for RunController core behavior."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

from app.core.models import ColumnInfo, FieldInfo, RowData, SheetInfo, TemplateInfo
from app.core.run_controller import ProgressEvent, RunConfig, RunController


class StubGraphClient:
    """Graph client stub that records send_mail calls."""

    def __init__(self, response_metadata: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response_metadata = response_metadata or {"status": "sent"}

    def send_mail(
        self,
        from_email: str,
        to_email: str,
        subject: str,
        html_body: str,
        save_to_sent: bool = True,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "from_email": from_email,
                "to_email": to_email,
                "subject": subject,
                "html_body": html_body,
                "save_to_sent": save_to_sent,
            }
        )
        return dict(self.response_metadata)


class StubGraphClientFactory:
    """Graph client factory stub that records instantiation calls."""

    def __init__(self, response_metadata: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.client = StubGraphClient(response_metadata=response_metadata)

    def __call__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
    ) -> StubGraphClient:
        self.calls.append((tenant_id, client_id, client_secret))
        return self.client


def _build_template_info() -> TemplateInfo:
    return TemplateInfo(
        template_name="template.docx",
        fields=[
            FieldInfo(key="Email", placeholder="Email"),
            FieldInfo(key="Name", placeholder="Name"),
        ],
    )


def _build_sheet_info() -> SheetInfo:
    return SheetInfo(
        name="Contacts",
        columns=[
            ColumnInfo(index=1, header="Email", key="Email", required=True),
            ColumnInfo(index=2, header="Name", key="Name", required=False),
        ],
        header_row_index=1,
    )


def _build_rows(emails: list[str]) -> list[RowData]:
    rows: list[RowData] = []
    for offset, email in enumerate(emails, start=2):
        rows.append(
            RowData(
                row_index=offset,
                values_by_key={"Email": email, "Name": f"User {offset}"},
            )
        )
    return rows


def _stub_merger(
    template_bytes: bytes,
    template_info: TemplateInfo,
    row: RowData,
) -> bytes:
    return f"merged-{row.row_index}".encode("utf-8")


def _stub_renderer(docx_bytes: bytes) -> str:
    return f"<p>{docx_bytes.decode('utf-8')}</p>"


def _read_csv(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def _build_config(tmp_path: Path, *, dry_run: bool = True) -> RunConfig:
    template_path = tmp_path / "template.docx"
    template_path.write_bytes(b"template-bytes")
    excel_path = tmp_path / "data.xlsx"
    return RunConfig(
        template_path=template_path,
        excel_path=excel_path,
        to_column_key="Email",
        from_email="sender@example.com",
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        subject_template="Hello {Name}",
        save_to_sent=True,
        dry_run=dry_run,
    )


def _build_controller(
    rows: list[RowData],
    sheet_info: SheetInfo,
    template_info: TemplateInfo,
    graph_factory: StubGraphClientFactory,
    audit_writer: Any | None = None,
) -> RunController:
    return RunController(
        graph_client_factory=graph_factory,
        template_analyzer=lambda _: template_info,
        excel_loader=lambda _path, _info: (sheet_info, rows),
        merger=_stub_merger,
        renderer=_stub_renderer,
        audit_writer=audit_writer,
    )


def test_dry_run_happy_path_processes_all_rows(tmp_path: Path) -> None:
    template_info = _build_template_info()
    sheet_info = _build_sheet_info()
    rows = _build_rows(
        [
            "ada@example.com",
            "grace@example.com",
            "alan@example.com",
        ]
    )
    graph_factory = StubGraphClientFactory()
    controller = _build_controller(rows, sheet_info, template_info, graph_factory)

    progress_events: list[ProgressEvent] = []

    def on_progress(event: ProgressEvent) -> None:
        progress_events.append(event)

    summary = controller.run(
        _build_config(tmp_path, dry_run=True),
        on_progress=on_progress,
    )

    assert summary.total_rows == 3
    assert summary.success_count == 3
    assert summary.failure_count == 0
    assert summary.processed_rows == 3
    assert [result.success for result in summary.results] == [True, True, True]
    assert graph_factory.calls == [], "Graph client factory should not run in dry-run mode."
    assert graph_factory.client.calls == [], "send_mail should not be called in dry-run mode."

    assert [event.processed for event in progress_events] == [1, 2, 3]
    assert [event.total for event in progress_events] == [3, 3, 3]
    assert [event.status for event in progress_events] == ["success", "success", "success"]
    assert [event.recipient for event in progress_events] == [
        row.values_by_key["Email"] for row in rows
    ]


def test_invalid_recipient_marks_failure_and_continues(tmp_path: Path) -> None:
    template_info = _build_template_info()
    sheet_info = _build_sheet_info()
    rows = _build_rows(["ada@example.com", "not-an-email", "grace@example.com"])
    graph_factory = StubGraphClientFactory()
    controller = _build_controller(rows, sheet_info, template_info, graph_factory)

    progress_events: list[ProgressEvent] = []

    def on_progress(event: ProgressEvent) -> None:
        progress_events.append(event)

    summary = controller.run(
        _build_config(tmp_path, dry_run=True),
        on_progress=on_progress,
    )

    assert summary.total_rows == 3
    assert summary.success_count == 2
    assert summary.failure_count == 1
    assert summary.processed_rows == 3
    assert summary.results[1].success is False
    assert summary.results[1].error is not None
    assert "Invalid recipient email" in str(summary.results[1].error)
    assert summary.results[2].success is True

    assert [event.processed for event in progress_events] == [1, 2, 3]
    assert [event.status for event in progress_events] == [
        "success",
        "invalid_recipient",
        "success",
    ]


def test_cancellation_stops_after_first_row(tmp_path: Path) -> None:
    template_info = _build_template_info()
    sheet_info = _build_sheet_info()
    rows = _build_rows(
        [
            "ada@example.com",
            "grace@example.com",
            "alan@example.com",
        ]
    )
    graph_factory = StubGraphClientFactory()
    controller = _build_controller(rows, sheet_info, template_info, graph_factory)

    class CancelToken:
        def __init__(self) -> None:
            self.cancelled = False

        def is_set(self) -> bool:
            return self.cancelled

    cancel_token = CancelToken()
    progress_events: list[ProgressEvent] = []

    def on_progress(event: ProgressEvent) -> None:
        progress_events.append(event)
        if event.processed == 1:
            cancel_token.cancelled = True

    summary = controller.run(
        _build_config(tmp_path, dry_run=True),
        on_progress=on_progress,
        cancel_token=cancel_token,
    )

    assert summary.total_rows == 3
    assert summary.processed_rows == 1
    assert summary.success_count == 1
    assert summary.failure_count == 0
    assert len(summary.results) == 1
    assert len(progress_events) == 1
    assert progress_events[0].processed == 1
    assert progress_events[0].total == 3


@pytest.mark.parametrize("email", ["", "  ", None])
def test_missing_recipient_marks_failure(tmp_path: Path, email: str | None) -> None:
    template_info = _build_template_info()
    sheet_info = _build_sheet_info()
    rows = _build_rows(["ada@example.com", "grace@example.com", "alan@example.com"])
    rows[1] = RowData(row_index=rows[1].row_index, values_by_key={"Email": email})
    graph_factory = StubGraphClientFactory()
    controller = _build_controller(rows, sheet_info, template_info, graph_factory)

    summary = controller.run(_build_config(tmp_path, dry_run=True))

    assert summary.success_count == 2
    assert summary.failure_count == 1
    assert summary.results[1].success is False
    assert summary.results[1].error is not None
    assert "Missing recipient" in str(summary.results[1].error)


def test_run_writes_audit_event_with_graph_request_id(tmp_path: Path) -> None:
    template_info = _build_template_info()
    sheet_info = _build_sheet_info()
    rows = _build_rows(["ada@example.com"])
    response_metadata = {
        "request_id": "req-123",
        "client_request_id": "client-456",
        "status_code": 202,
    }
    graph_factory = StubGraphClientFactory(response_metadata=response_metadata)
    audit_events: list[dict[str, Any]] = []

    def audit_writer(event: dict[str, Any]) -> None:
        audit_events.append(event)

    controller = _build_controller(
        rows,
        sheet_info,
        template_info,
        graph_factory,
        audit_writer=audit_writer,
    )

    summary = controller.run(_build_config(tmp_path, dry_run=False))

    assert summary.success_count == 1
    assert summary.failure_count == 0
    result = summary.results[0]
    assert result.graph_request_id == "req-123"
    assert result.graph_client_request_id == "client-456"

    assert len(audit_events) == 1
    event = audit_events[0]
    assert event["row_index"] == 2
    assert event["recipient"] == "ada@example.com"
    assert event["status"] == "success"
    assert event["graph_request_id"] == "req-123"
    assert event["graph_client_request_id"] == "client-456"


def test_run_dir_writes_results_csv(tmp_path: Path) -> None:
    template_info = _build_template_info()
    sheet_info = _build_sheet_info()
    rows = _build_rows(["ada@example.com"])
    graph_factory = StubGraphClientFactory()
    controller = _build_controller(rows, sheet_info, template_info, graph_factory)
    run_dir = tmp_path / "run-output"

    summary = controller.run(
        _build_config(tmp_path, dry_run=True),
        run_dir=run_dir,
    )

    assert summary.run_dir == run_dir
    assert summary.results_csv_path == run_dir / "results.csv"
    assert run_dir.exists()

    csv_path = summary.results_csv_path
    assert csv_path is not None
    assert csv_path.exists()

    rows = _read_csv(csv_path)
    assert rows, "results.csv should contain a header row and data rows."

    header = rows[0]
    expected_header = [
        "row_index",
        "to_email",
        "status",
        "error",
        "identifier_序号",
        "identifier_姓名",
        "subject",
        "graph_request_id",
        "graph_client_request_id",
    ]
    assert (
        header == expected_header
    ), f"Expected header columns {expected_header!r}, got {header!r}."
    assert len(rows) == 2, "results.csv should contain one header row plus one data row."

    index_row = header.index("row_index")
    index_email = header.index("to_email")
    index_status = header.index("status")
    index_subject = header.index("subject")
    index_request_id = header.index("graph_request_id")
    index_client_request_id = header.index("graph_client_request_id")

    data_row = rows[1]
    assert data_row[index_row] == "2"
    assert data_row[index_email] == "ada@example.com"
    assert data_row[index_status] == "success"
    assert data_row[index_subject] == "Hello User 2"
    assert data_row[index_request_id] == ""
    assert data_row[index_client_request_id] == ""

