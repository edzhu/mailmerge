"""Data models for the mail-merge emailer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Sequence


@dataclass
class FieldInfo:
    """Describes a merge field referenced in a template."""

    key: str
    placeholder: str
    label: Optional[str] = None
    required: bool = True
    source: Optional[str] = None
    format_hint: Optional[str] = None


@dataclass
class TemplateInfo:
    """Summarizes a template and the fields it requires."""

    template_name: str
    fields: Sequence[FieldInfo] = field(default_factory=list)
    subject_template: Optional[str] = None
    body_template: Optional[str] = None

    @property
    def fields_by_key(self) -> Dict[str, FieldInfo]:
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
    header_row_index: int = 1
    row_count: Optional[int] = None

    @property
    def columns_by_key(self) -> Dict[str, ColumnInfo]:
        """Return a mapping of column keys to column metadata."""

        return {column.key: column for column in self.columns}


@dataclass
class RowData:
    """Represents a single row of input data keyed by column key."""

    row_index: int
    values_by_key: Mapping[str, Optional[str]]


@dataclass
class RowResult:
    """Result of rendering and sending a single row."""

    row: RowData
    success: bool
    rendered_subject: Optional[str] = None
    rendered_body: Optional[str] = None
    error: Optional[Exception] = None


@dataclass
class RunSummary:
    """Aggregated results from a mail-merge run."""

    total_rows: int
    success_count: int
    failure_count: int
    results: Sequence[RowResult] = field(default_factory=list)

    @property
    def processed_rows(self) -> int:
        """Return the number of processed rows."""

        return self.success_count + self.failure_count
