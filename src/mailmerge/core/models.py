"""Data models for the mail-merge emailer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from numbers import Number
from pathlib import Path

CellValue = str | Number | datetime | date | None


@dataclass
class FieldInfo:
    """Describes a merge field referenced in a template."""

    key: str
    placeholder: str
    label: str | None = None
    required: bool = True
    source: str | None = None
    format_hint: str | None = None


@dataclass
class TemplateInfo:
    """Summarizes a template and the fields it requires."""

    template_name: str
    fields: Sequence[FieldInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    subject_template: str | None = None
    body_template: str | None = None

    @property
    def fields_by_key(self) -> dict[str, FieldInfo]:
        """Return a mapping of field keys to field metadata."""

        return {field_info.key: field_info for field_info in self.fields}


@dataclass
class ColumnInfo:
    """Describes a spreadsheet column used for mail-merge data."""

    index: int
    header: str
    key: str
    required: bool = True


@dataclass
class SheetInfo:
    """Metadata about a spreadsheet sheet and its columns."""

    name: str
    columns: Sequence[ColumnInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    header_row_index: int = 1
    row_count: int | None = None

    @property
    def columns_by_key(self) -> dict[str, ColumnInfo]:
        """Return a mapping of column keys to column metadata."""

        return {column.key: column for column in self.columns}


@dataclass
class RowData:
    """Represents a single row of input data keyed by column key."""

    row_index: int
    values_by_key: Mapping[str, CellValue]


@dataclass
class RowResult:
    """Result of rendering and sending a single row."""

    row: RowData
    success: bool
    rendered_subject: str | None = None
    rendered_body: str | None = None
    error: Exception | None = None
    graph_request_id: str | None = None
    graph_client_request_id: str | None = None


@dataclass
class RunSummary:
    """Aggregated results from a mail-merge run."""

    total_rows: int
    success_count: int
    failure_count: int
    results: Sequence[RowResult] = field(default_factory=list)
    run_dir: Path | None = None
    results_csv_path: Path | None = None

    @property
    def processed_rows(self) -> int:
        """Return the number of processed rows."""

        return self.success_count + self.failure_count
