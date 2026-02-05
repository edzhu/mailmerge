"""Run controller orchestration for executing a mail merge."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol

from app.core.canonicalize import canonicalize
from app.core.errors import ConfigurationError, MailMergeError, TemplateValidationError
from app.core.excel_loader import load_matching_sheet
from app.core.graph_client import GraphClient
from app.core.html_renderer import docx_bytes_to_html
from app.core.merge_engine import merge_docx_bytes
from app.core.models import RowData, RowResult, RunSummary, SheetInfo, TemplateInfo
from app.core.template_analyzer import analyze_template
from app.core.text_templating import render_subject
from app.core.validation import is_valid_email


class GraphClientProtocol(Protocol):
    """Protocol describing the Graph client API used by the controller."""

    def send_mail(
        self,
        from_email: str,
        to_email: str,
        subject: str,
        html_body: str,
        save_to_sent: bool = True,
    ) -> Mapping[str, Any]:
        """Send a mail message."""
        ...


GraphClientFactory = Callable[[str, str, str], GraphClientProtocol]
TemplateAnalyzer = Callable[[Path], TemplateInfo]
ExcelLoader = Callable[[Path, TemplateInfo], tuple[SheetInfo, list[RowData]]]
Merger = Callable[[bytes, TemplateInfo, RowData], bytes]
Renderer = Callable[[bytes], str]
ProgressCallback = Callable[["ProgressEvent"], None]
AuditWriter = Callable[[Mapping[str, Any]], None]


@dataclass
class RunConfig:
    """Configuration for a mail-merge run."""

    template_path: Path
    excel_path: Path
    to_column_key: str
    from_email: str
    tenant_id: str
    client_id: str
    client_secret: str
    subject_template: str
    save_to_sent: bool = True
    dry_run: bool = False

    def __post_init__(self) -> None:
        try:
            self.template_path = Path(self.template_path)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("template_path must be a valid path.") from exc
        try:
            self.excel_path = Path(self.excel_path)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("excel_path must be a valid path.") from exc
        self.to_column_key = canonicalize(self.to_column_key)


@dataclass
class ProgressEvent:
    """Progress information emitted after each processed row."""

    row_index: int
    processed: int
    total: int
    recipient: str
    status: str


@dataclass
class _RowOutcome:
    recipient: str
    status: str
    result: RowResult


class RunController:
    """Coordinate the mail-merge workflow."""

    def __init__(
        self,
        graph_client_factory: Optional[GraphClientFactory] = None,
        template_analyzer: Optional[TemplateAnalyzer] = None,
        excel_loader: Optional[ExcelLoader] = None,
        merger: Optional[Merger] = None,
        renderer: Optional[Renderer] = None,
        logger: Optional[logging.Logger] = None,
        audit_writer: Optional[AuditWriter] = None,
    ) -> None:
        self._graph_client_factory = graph_client_factory or _default_graph_client_factory
        self._template_analyzer = template_analyzer or analyze_template
        self._excel_loader = excel_loader or load_matching_sheet
        self._merger = merger or merge_docx_bytes
        self._renderer = renderer or docx_bytes_to_html
        self._logger = logger or logging.getLogger(__name__)
        self._audit_writer = audit_writer

    def run(
        self,
        config: RunConfig,
        on_progress: Optional[ProgressCallback] = None,
        cancel_token: Optional[object] = None,
    ) -> RunSummary:
        """Execute a mail-merge run and return a summary."""
        try:
            _validate_run_config(config)

            template_bytes = _load_template_bytes(config.template_path)
            template_info = _safe_analyze_template(
                self._template_analyzer,
                config.template_path,
            )
            sheet_info, rows = _safe_load_rows(
                self._excel_loader,
                config.excel_path,
                template_info,
            )
            _ensure_recipient_column(config.to_column_key, sheet_info)

            graph_client: Optional[GraphClientProtocol] = None
            if not config.dry_run:
                graph_client = self._graph_client_factory(
                    config.tenant_id,
                    config.client_id,
                    config.client_secret,
                )

            total_rows = len(rows)
            results: list[RowResult] = []
            success_count = 0
            failure_count = 0

            for row in rows:
                if _is_cancelled(cancel_token):
                    self._logger.info("Run cancelled before row %s.", row.row_index)
                    break

                outcome = _process_row(
                    row=row,
                    config=config,
                    to_column_key=config.to_column_key,
                    template_bytes=template_bytes,
                    template_info=template_info,
                    merger=self._merger,
                    renderer=self._renderer,
                    graph_client=graph_client,
                )
                results.append(outcome.result)
                if outcome.result.success:
                    success_count += 1
                else:
                    failure_count += 1

                processed = success_count + failure_count
                event = ProgressEvent(
                    row_index=row.row_index,
                    processed=processed,
                    total=total_rows,
                    recipient=outcome.recipient,
                    status=outcome.status,
                )
                _emit_progress(on_progress, event, self._logger)
                _write_audit_event(self._audit_writer, row, outcome, self._logger)

            return RunSummary(
                total_rows=total_rows,
                success_count=success_count,
                failure_count=failure_count,
                results=results,
            )
        except MailMergeError:
            raise
        except Exception as exc:  # pragma: no cover - defensive guardrail
            raise MailMergeError("Mail merge run failed.") from exc


def _default_graph_client_factory(
    tenant_id: str,
    client_id: str,
    client_secret: str,
) -> GraphClientProtocol:
    """Create a Graph client using the provided credentials."""
    return GraphClient(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )


def _validate_run_config(config: RunConfig) -> None:
    if not config.template_path:
        raise ConfigurationError("template_path is required.")
    if not config.excel_path:
        raise ConfigurationError("excel_path is required.")
    if not config.to_column_key:
        raise ConfigurationError("to_column_key is required.")
    if config.from_email and not is_valid_email(config.from_email):
        raise ConfigurationError("from_email must be a valid email address.")
    if not config.dry_run:
        if not config.from_email:
            raise ConfigurationError("from_email is required.")
        if not config.tenant_id:
            raise ConfigurationError("tenant_id is required.")
        if not config.client_id:
            raise ConfigurationError("client_id is required.")
        if not config.client_secret:
            raise ConfigurationError("client_secret is required.")


def _load_template_bytes(template_path: Path) -> bytes:
    try:
        template_bytes = template_path.read_bytes()
    except FileNotFoundError as exc:
        raise TemplateValidationError(
            f"Template not found: {template_path}"
        ) from exc
    except OSError as exc:
        raise TemplateValidationError(
            f"Unable to read template: {template_path}"
        ) from exc
    if not template_bytes:
        raise TemplateValidationError(f"Template is empty: {template_path}")
    return template_bytes


def _safe_analyze_template(
    analyzer: TemplateAnalyzer,
    template_path: Path,
) -> TemplateInfo:
    try:
        return analyzer(template_path)
    except MailMergeError:
        raise
    except Exception as exc:  # pragma: no cover - defensive guardrail
        raise TemplateValidationError("Template analysis failed.") from exc


def _safe_load_rows(
    loader: ExcelLoader,
    excel_path: Path,
    template_info: TemplateInfo,
) -> tuple[SheetInfo, list[RowData]]:
    try:
        return loader(excel_path, template_info)
    except MailMergeError:
        raise
    except Exception as exc:  # pragma: no cover - defensive guardrail
        raise MailMergeError("Failed to load spreadsheet data.") from exc


def _ensure_recipient_column(to_column_key: str, sheet_info: SheetInfo) -> None:
    if to_column_key not in sheet_info.columns_by_key:
        raise ConfigurationError(
            f"Recipient column '{to_column_key}' not found in sheet '{sheet_info.name}'."
        )


def _process_row(
    *,
    row: RowData,
    config: RunConfig,
    to_column_key: str,
    template_bytes: bytes,
    template_info: TemplateInfo,
    merger: Merger,
    renderer: Renderer,
    graph_client: Optional[GraphClientProtocol],
) -> _RowOutcome:
    recipient = _resolve_recipient(row, to_column_key)
    if not recipient:
        error = MailMergeError(
            f"Missing recipient value for column '{to_column_key}'."
        )
        result = RowResult(row=row, success=False, error=error)
        return _RowOutcome(recipient="", status="missing_recipient", result=result)
    if not is_valid_email(recipient):
        error = MailMergeError(f"Invalid recipient email: {recipient}")
        result = RowResult(row=row, success=False, error=error)
        return _RowOutcome(
            recipient=recipient,
            status="invalid_recipient",
            result=result,
        )

    rendered_subject: Optional[str] = None
    rendered_body: Optional[str] = None

    try:
        merged_bytes = merger(template_bytes, template_info, row)
        rendered_body = renderer(merged_bytes)
        rendered_subject = render_subject(config.subject_template, row)
        if not config.dry_run:
            if graph_client is None:
                raise ConfigurationError("Graph client is not configured.")
            graph_client.send_mail(
                config.from_email,
                recipient,
                rendered_subject,
                rendered_body,
                config.save_to_sent,
            )
        result = RowResult(
            row=row,
            success=True,
            rendered_subject=rendered_subject,
            rendered_body=rendered_body,
        )
        return _RowOutcome(recipient=recipient, status="success", result=result)
    except MailMergeError as exc:
        return _failure_outcome(row, recipient, rendered_subject, rendered_body, exc)
    except Exception as exc:  # pragma: no cover - defensive guardrail
        error = MailMergeError(
            f"Unexpected error while processing row {row.row_index}."
        )
        error.__cause__ = exc
        return _failure_outcome(row, recipient, rendered_subject, rendered_body, error)


def _resolve_recipient(row: RowData, to_column_key: str) -> str:
    value = row.values_by_key.get(to_column_key)
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _failure_outcome(
    row: RowData,
    recipient: str,
    rendered_subject: Optional[str],
    rendered_body: Optional[str],
    error: Exception,
) -> _RowOutcome:
    result = RowResult(
        row=row,
        success=False,
        rendered_subject=rendered_subject,
        rendered_body=rendered_body,
        error=error,
    )
    return _RowOutcome(recipient=recipient, status="failure", result=result)


def _emit_progress(
    callback: Optional[ProgressCallback],
    event: ProgressEvent,
    logger: logging.Logger,
) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except Exception:  # pragma: no cover - avoid interrupting the run
        logger.warning("Progress callback raised an exception.")


def _write_audit_event(
    audit_writer: Optional[AuditWriter],
    row: RowData,
    outcome: _RowOutcome,
    logger: logging.Logger,
) -> None:
    if audit_writer is None:
        return
    event: dict[str, Any] = {
        "row_index": row.row_index,
        "recipient": outcome.recipient,
        "status": outcome.status,
        "error": str(outcome.result.error) if outcome.result.error else None,
    }
    try:
        if callable(audit_writer):
            audit_writer(event)
        elif hasattr(audit_writer, "write_event"):
            audit_writer.write_event(event)
        elif hasattr(audit_writer, "write"):
            audit_writer.write(event)
        else:
            logger.debug("Audit writer does not expose a callable interface.")
    except Exception:  # pragma: no cover - avoid interrupting the run
        logger.warning("Audit writer raised an exception for row %s.", row.row_index)


def _is_cancelled(cancel_token: Optional[object]) -> bool:
    if cancel_token is None:
        return False
    if callable(cancel_token):
        try:
            return bool(cancel_token())
        except Exception:
            return False
    for attr_name in ("is_cancelled", "is_canceled", "is_set"):
        if hasattr(cancel_token, attr_name):
            attr = getattr(cancel_token, attr_name)
            try:
                return bool(attr() if callable(attr) else attr)
            except Exception:
                return False
    return False


__all__ = [
    "GraphClientProtocol",
    "ProgressEvent",
    "RunConfig",
    "RunController",
    "RunSummary",
    "RowResult",
]
