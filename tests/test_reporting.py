"""Tests for results CSV reporting."""

from __future__ import annotations

import csv
from pathlib import Path

from mailmerge.core.models import RowData, RowResult, RunSummary
from mailmerge.core.reporting import write_results_csv


def _build_summary() -> RunSummary:
    row_one = RowData(
        row_index=2,
        values_by_key={"email": "ada@example.com", "序号": "A-01", "姓名": "Ada"},
    )
    result_one = RowResult(
        row=row_one,
        success=True,
        rendered_subject="Hello Ada",
    )

    row_two = RowData(
        row_index=3,
        values_by_key={"email": "grace@example.com", "序号": "B-02", "姓名": "Grace"},
    )
    result_two = RowResult(
        row=row_two,
        success=False,
        error=RuntimeError("SMTP failed"),
    )

    row_three = RowData(
        row_index=4,
        values_by_key={"email": "linus@example.com", "序号": "C-03", "姓名": "Linus"},
    )
    result_three = RowResult(row=row_three, success=False)
    result_three.status = "skipped"

    return RunSummary(
        total_rows=3,
        success_count=1,
        failure_count=2,
        results=[result_one, result_two, result_three],
        run_dir=None,
        results_csv_path=None,
    )


def _read_csv(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def test_write_results_csv_writes_expected_rows(tmp_path: Path) -> None:
    summary = _build_summary()

    csv_path = write_results_csv(tmp_path, summary)

    expected_path = tmp_path / "results.csv"
    assert (
        csv_path == expected_path
    ), "write_results_csv should return the full path to results.csv."
    assert expected_path.exists(), "results.csv should be created in the run directory."

    rows = _read_csv(expected_path)
    assert rows, "results.csv should contain a header row and data rows."

    header = rows[0]
    include_subject = any(
        hasattr(result, "rendered_subject") or hasattr(result, "subject")
        for result in summary.results
    )
    include_request_ids = any(
        hasattr(result, "graph_request_id") or hasattr(result, "graph_client_request_id")
        for result in summary.results
    )
    expected_header = [
        "row_index",
        "to_email",
        "status",
        "error",
        "identifier_序号",
        "identifier_姓名",
    ]
    if include_subject:
        expected_header.append("subject")
    if include_request_ids:
        expected_header.extend(["graph_request_id", "graph_client_request_id"])

    assert (
        header == expected_header
    ), f"Expected header columns {expected_header!r}, got {header!r}."

    assert len(rows) == 4, "results.csv should contain one header row plus 3 data rows."

    index_row = header.index("row_index")
    index_email = header.index("to_email")
    index_status = header.index("status")
    index_error = header.index("error")
    index_request_id = header.index("graph_request_id")
    index_client_request_id = header.index("graph_client_request_id")

    first_row, second_row, third_row = rows[1:4]

    assert first_row[index_row] == "2"
    assert first_row[index_email] == "ada@example.com"
    assert first_row[index_status] == "success"
    assert first_row[index_error] == ""
    assert first_row[index_request_id] == ""
    assert first_row[index_client_request_id] == ""

    assert second_row[index_row] == "3"
    assert second_row[index_email] == "grace@example.com"
    assert second_row[index_status] == "failure"
    assert second_row[index_error] == "SMTP failed"
    assert second_row[index_request_id] == ""
    assert second_row[index_client_request_id] == ""

    assert third_row[index_row] == "4"
    assert third_row[index_email] == "linus@example.com"
    assert third_row[index_status] == "skipped"
    assert third_row[index_error] == ""
    assert third_row[index_request_id] == ""
    assert third_row[index_client_request_id] == ""


def test_write_results_csv_includes_request_ids_when_present(tmp_path: Path) -> None:
    row = RowData(row_index=2, values_by_key={"email": "ada@example.com"})
    result = RowResult(
        row=row,
        success=True,
        rendered_subject="Hello Ada",
        graph_request_id="req-123",
        graph_client_request_id="client-456",
    )
    summary = RunSummary(
        total_rows=1,
        success_count=1,
        failure_count=0,
        results=[result],
        run_dir=None,
        results_csv_path=None,
    )

    csv_path = write_results_csv(tmp_path, summary)

    rows = _read_csv(csv_path)
    header = rows[0]
    index_request_id = header.index("graph_request_id")
    index_client_request_id = header.index("graph_client_request_id")
    data_row = rows[1]

    assert data_row[index_request_id] == "req-123"
    assert data_row[index_client_request_id] == "client-456"
