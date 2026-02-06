"""Main window for the PySide6 GUI."""

from __future__ import annotations

from pathlib import Path
import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

from app.core.errors import ExcelValidationError, MailMergeError
from app.core.excel_loader import load_matching_sheet
from app.core.logging_setup import AuditWriter, configure_logging, create_run_directory
from app.core.models import RowData, SheetInfo, TemplateInfo
from app.core.run_controller import ProgressEvent, RunConfig, RunController, RunSummary
from app.core.template_analyzer import analyze_template
from app.ui.run_logic import (
    build_run_config_from_inputs,
    is_from_email_valid,
    run_controller_with_cancel,
)
from app.ui.to_column_logic import choose_to_columns
from app.ui.preview_dialog import PreviewDialog

_DEFAULT_SUBJECT_TEMPLATE = "薪酬单 {年份}年{月份}月 - {姓名}"


class _TemplateAnalysisSignals(QObject):
    """Signals for template analysis tasks."""

    finished = Signal(object)
    error = Signal(str)


class _ExcelLoadSignals(QObject):
    """Signals for Excel loading tasks."""

    finished = Signal(object, object)
    error = Signal(str)


class _RunSignals(QObject):
    """Signals for run execution tasks."""

    progress = Signal(object)
    finished = Signal(object)
    error = Signal(str)


def _find_excel_validation_error(
    exc: BaseException,
) -> ExcelValidationError | None:
    """Return the first ExcelValidationError in an exception chain."""

    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        if isinstance(current, ExcelValidationError):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


def _format_excel_load_error(exc: BaseException) -> str:
    """Format Excel load errors for user-facing dialogs."""

    validation_error = _find_excel_validation_error(exc)
    if validation_error is not None:
        message = str(validation_error).strip()
        if message:
            return message
    if isinstance(exc, MailMergeError):
        message = str(exc).strip()
        if message:
            return message
    return "Failed to load spreadsheet."


class _TemplateAnalysisWorker(QRunnable):
    """Analyze templates in a background worker."""

    def __init__(self, template_path: Path) -> None:
        super().__init__()
        self.signals = _TemplateAnalysisSignals()
        self._template_path = Path(template_path)

    @Slot()
    def run(self) -> None:
        try:
            template_info = analyze_template(self._template_path)
        except MailMergeError as exc:
            self.signals.error.emit(str(exc))
            return
        except Exception:
            self.signals.error.emit("Template analysis failed.")
            return
        self.signals.finished.emit(template_info)


class _ExcelLoadWorker(QRunnable):
    """Load spreadsheet metadata in a background worker."""

    def __init__(self, excel_path: Path, template_info: TemplateInfo) -> None:
        super().__init__()
        self.signals = _ExcelLoadSignals()
        self._excel_path = Path(excel_path)
        self._template_info = template_info

    @Slot()
    def run(self) -> None:
        try:
            sheet_info, rows = load_matching_sheet(self._excel_path, self._template_info)
        except MailMergeError as exc:
            self.signals.error.emit(_format_excel_load_error(exc))
            return
        except Exception as exc:
            self.signals.error.emit(_format_excel_load_error(exc))
            return
        self.signals.finished.emit(sheet_info, rows)


class _RunWorker(QRunnable):
    """Execute the run controller workflow on a background thread."""

    def __init__(self, config: RunConfig, cancel_token: threading.Event) -> None:
        super().__init__()
        self.signals = _RunSignals()
        self._config = config
        self._cancel_token = cancel_token

    @Slot()
    def run(self) -> None:
        try:
            run_dir = create_run_directory(None)
            logger = configure_logging(run_dir)
            audit_writer = AuditWriter(run_dir)
            controller = RunController(logger=logger, audit_writer=audit_writer)
            summary = run_controller_with_cancel(
                controller=controller,
                config=self._config,
                on_progress=self._emit_progress,
                cancel_token=self._cancel_token,
            )
        except MailMergeError as exc:
            self.signals.error.emit(str(exc))
            return
        except Exception:
            self.signals.error.emit("Mail merge run failed.")
            return
        self.signals.finished.emit(summary)

    def _emit_progress(self, event: ProgressEvent) -> None:
        self.signals.progress.emit(event)


class MainWindow(QMainWindow):
    """Main window for the mail-merge emailer GUI."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mail-merge emailer")

        self._thread_pool = QThreadPool.globalInstance()
        self._template_request_id = 0
        self._excel_request_id = 0
        self._template_info: TemplateInfo | None = None
        self._template_warnings: list[str] = []
        self._template_warning_dialog_request_id: int | None = None
        self._template_warning_dialog: QMessageBox | None = None
        self._sheet_info: SheetInfo | None = None
        self._loaded_rows: list[RowData] = []
        self._sheet_warnings: list[str] = []
        self._processing = False
        self._cancel_event: threading.Event | None = None
        self._progress_dialog: QProgressDialog | None = None

        self._template_path = QLineEdit()
        self._template_path.setPlaceholderText("Template (.docx)")
        self._template_button = QPushButton("Browse...")
        self._template_button.clicked.connect(self._pick_template)

        self._excel_path = QLineEdit()
        self._excel_path.setPlaceholderText("Spreadsheet (.xlsx)")
        self._excel_button = QPushButton("Browse...")
        self._excel_button.clicked.connect(self._pick_excel)

        self._to_column = QComboBox()
        self._to_column.setEditable(True)

        self._subject_template = QLineEdit()
        self._subject_template.setPlaceholderText("Subject template")
        self._subject_template.setText(_DEFAULT_SUBJECT_TEMPLATE)

        self._tenant_id = QLineEdit()
        self._client_id = QLineEdit()
        self._client_secret = QLineEdit()
        self._client_secret.setEchoMode(QLineEdit.Password)
        self._from_email = QLineEdit()

        self._preview_button = QPushButton("Preview")
        self._process_button = QPushButton("Process")
        self._preview_button.clicked.connect(self._on_preview_clicked)
        self._process_button.clicked.connect(self._on_process_clicked)

        self._build_layout()
        self._initialize_state()
        self._wire_signals()

    def _build_layout(self) -> None:
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        files_group = QGroupBox("Files")
        files_layout = QFormLayout(files_group)
        files_layout.addRow(
            "Template",
            self._picker_row(self._template_path, self._template_button),
        )
        files_layout.addRow(
            "Excel",
            self._picker_row(self._excel_path, self._excel_button),
        )
        main_layout.addWidget(files_group)

        merge_group = QGroupBox("Merge settings")
        merge_layout = QFormLayout(merge_group)
        merge_layout.addRow("To column", self._to_column)
        merge_layout.addRow("Subject template", self._subject_template)
        main_layout.addWidget(merge_group)

        credentials_group = QGroupBox("Credentials")
        credentials_layout = QFormLayout(credentials_group)
        credentials_layout.addRow("Tenant ID", self._tenant_id)
        credentials_layout.addRow("Client ID", self._client_id)
        credentials_layout.addRow("Client secret", self._client_secret)
        credentials_layout.addRow("From email", self._from_email)
        main_layout.addWidget(credentials_group)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self._preview_button)
        button_layout.addWidget(self._process_button)
        main_layout.addLayout(button_layout)

        main_layout.addStretch(1)
        self.setCentralWidget(central_widget)
        self.statusBar().showMessage("Ready")

    def _initialize_state(self) -> None:
        self._clear_to_column()
        self._set_excel_controls_enabled(False)
        self._set_to_column_enabled(False)
        self._process_button.setEnabled(False)
        self._update_process_state()

    def _wire_signals(self) -> None:
        self._template_path.textChanged.connect(self._on_template_path_changed)
        self._excel_path.textChanged.connect(self._on_excel_path_changed)
        self._to_column.currentTextChanged.connect(self._update_process_state)
        self._from_email.textChanged.connect(self._update_process_state)
        self._tenant_id.textChanged.connect(self._update_process_state)
        self._client_id.textChanged.connect(self._update_process_state)
        self._client_secret.textChanged.connect(self._update_process_state)

    def _picker_row(self, line_edit: QLineEdit, button: QPushButton) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        layout.addWidget(button)
        return row

    def _set_excel_controls_enabled(self, enabled: bool) -> None:
        self._excel_path.setEnabled(enabled)
        self._excel_button.setEnabled(enabled)

    def _set_to_column_enabled(self, enabled: bool) -> None:
        self._to_column.setEnabled(enabled)

    def _apply_dependent_enable_state(self) -> None:
        self._set_excel_controls_enabled(self._template_info is not None)
        self._set_to_column_enabled(self._sheet_info is not None)

    def _clear_excel_path(self) -> None:
        self._excel_path.blockSignals(True)
        self._excel_path.setText("")
        self._excel_path.blockSignals(False)

    def _clear_to_column(self) -> None:
        self._to_column.blockSignals(True)
        self._to_column.clear()
        self._to_column.addItem("")
        self._to_column.setCurrentIndex(0)
        self._to_column.blockSignals(False)

    def _reset_excel_state(self) -> None:
        self._sheet_info = None
        self._loaded_rows = []
        self._sheet_warnings = []
        self._excel_request_id += 1
        self._clear_excel_path()
        self._clear_to_column()
        self._set_to_column_enabled(False)
        self._set_excel_controls_enabled(False)

    def _clear_template_warnings(self) -> None:
        self._template_warnings = []
        self._template_warning_dialog_request_id = None
        self._dismiss_template_warning_dialog()

    def _dismiss_template_warning_dialog(self) -> None:
        if self._template_warning_dialog is None:
            return
        dialog = self._template_warning_dialog
        self._template_warning_dialog = None
        dialog.close()
        dialog.deleteLater()

    def _pick_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select template",
            "",
            "Word Documents (*.docx);;All Files (*)",
        )
        if path:
            self._template_path.setText(path)

    def _pick_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select spreadsheet",
            "",
            "Excel Files (*.xlsx *.xls);;All Files (*)",
        )
        if path:
            self._excel_path.setText(path)

    def _on_template_path_changed(self, value: str) -> None:
        self._template_request_id += 1
        request_id = self._template_request_id
        self._template_info = None
        self._reset_excel_state()
        self._clear_template_warnings()

        template_value = value.strip()
        if not template_value:
            self.statusBar().showMessage("Select a template to continue.")
            self._update_process_state()
            return

        template_path = Path(template_value)
        if not template_path.exists():
            self.statusBar().showMessage("Template file not found.", 5000)
            self._update_process_state()
            return

        self.statusBar().showMessage("Analyzing template...")
        worker = _TemplateAnalysisWorker(template_path)
        worker.signals.finished.connect(
            lambda info, rid=request_id: self._handle_template_success(rid, info)
        )
        worker.signals.error.connect(
            lambda message, rid=request_id: self._handle_template_error(rid, message)
        )
        self._thread_pool.start(worker)

    def _handle_template_success(self, request_id: int, info: TemplateInfo) -> None:
        if request_id != self._template_request_id:
            return
        self._template_info = info
        self._template_warnings = list(info.warnings)
        self._set_excel_controls_enabled(True)
        if not self._subject_template.text().strip():
            self._subject_template.setText(_DEFAULT_SUBJECT_TEMPLATE)
        message = f"Template '{info.template_name}' ready."
        duration = 5000
        if self._template_warnings:
            message = f"{message} {' '.join(self._template_warnings)}"
            duration = 8000
            if self._template_warning_dialog_request_id != request_id:
                self._template_warning_dialog_request_id = request_id
                self._show_template_warning_dialog(self._template_warnings)
        self.statusBar().showMessage(message, duration)
        self._update_process_state()

    def _handle_template_error(self, request_id: int, message: str) -> None:
        if request_id != self._template_request_id:
            return
        self._template_info = None
        self._clear_template_warnings()
        self._reset_excel_state()
        self.statusBar().showMessage("Template analysis failed.", 8000)
        self._show_error_dialog("Template error", message)
        self._update_process_state()

    def _on_excel_path_changed(self, value: str) -> None:
        self._excel_request_id += 1
        request_id = self._excel_request_id
        self._sheet_info = None
        self._loaded_rows = []
        self._sheet_warnings = []
        self._clear_to_column()
        self._set_to_column_enabled(False)

        if self._template_info is None:
            self._update_process_state()
            return

        excel_value = value.strip()
        if not excel_value:
            self.statusBar().showMessage("Select a spreadsheet to continue.")
            self._update_process_state()
            return

        excel_path = Path(excel_value)
        if not excel_path.exists():
            self.statusBar().showMessage("Spreadsheet file not found.", 5000)
            self._update_process_state()
            return

        self.statusBar().showMessage("Loading spreadsheet...")
        worker = _ExcelLoadWorker(excel_path, self._template_info)
        worker.signals.finished.connect(
            lambda sheet_info, rows, rid=request_id: self._handle_excel_success(
                rid,
                sheet_info,
                rows,
            )
        )
        worker.signals.error.connect(
            lambda message, rid=request_id: self._handle_excel_error(rid, message)
        )
        self._thread_pool.start(worker)

    def _handle_excel_success(
        self,
        request_id: int,
        sheet_info: SheetInfo,
        rows: list[RowData],
    ) -> None:
        if request_id != self._excel_request_id:
            return
        self._sheet_info = sheet_info
        self._loaded_rows = rows
        warnings = self._populate_to_column(sheet_info, rows)
        self._sheet_warnings = warnings
        self._set_to_column_enabled(True)
        message = f"Loaded '{sheet_info.name}' with {len(rows)} rows."
        duration = 5000
        if self._sheet_warnings:
            message = f"{message} {' '.join(self._sheet_warnings)}"
            duration = 8000
        self.statusBar().showMessage(message, duration)
        self._update_process_state()

    def _handle_excel_error(self, request_id: int, message: str) -> None:
        if request_id != self._excel_request_id:
            return
        self._sheet_info = None
        self._loaded_rows = []
        self._sheet_warnings = []
        self._clear_to_column()
        self._set_to_column_enabled(False)
        self.statusBar().showMessage("Spreadsheet load failed.", 8000)
        self._show_error_dialog("Spreadsheet error", message)
        self._update_process_state()

    def _populate_to_column(
        self,
        sheet_info: SheetInfo,
        rows: list[RowData],
    ) -> list[str]:
        columns, warnings = choose_to_columns(sheet_info, rows)
        self._to_column.blockSignals(True)
        self._to_column.clear()
        self._to_column.addItem("")
        for column in columns:
            self._to_column.addItem(column.header, column.key)
        self._to_column.setCurrentIndex(0)
        self._to_column.blockSignals(False)
        return warnings

    def _selected_to_column_key(self) -> str:
        data = self._to_column.currentData()
        if data is not None:
            text = str(data).strip()
            if text:
                return text
        return self._to_column.currentText().strip()

    def _credentials_ready(self) -> bool:
        return bool(
            self._tenant_id.text().strip()
            and self._client_id.text().strip()
            and self._client_secret.text().strip()
        )

    def _from_email_valid(self) -> bool:
        return is_from_email_valid(self._from_email.text())

    def _update_email_style(self) -> None:
        value = self._from_email.text().strip()
        if not value:
            self._from_email.setStyleSheet("")
            return
        if is_from_email_valid(value):
            self._from_email.setStyleSheet("")
            return
        self._from_email.setStyleSheet("border: 1px solid #d9534f;")

    def _update_process_state(self) -> None:
        self._update_email_style()
        if self._processing:
            self._process_button.setEnabled(False)
            return
        ready = (
            self._template_info is not None
            and self._sheet_info is not None
            and bool(self._selected_to_column_key())
            and self._from_email_valid()
            and self._credentials_ready()
        )
        self._process_button.setEnabled(ready)

    def _set_processing(self, processing: bool) -> None:
        self._processing = processing
        self._template_path.setEnabled(not processing)
        self._template_button.setEnabled(not processing)
        self._subject_template.setEnabled(not processing)
        self._tenant_id.setEnabled(not processing)
        self._client_id.setEnabled(not processing)
        self._client_secret.setEnabled(not processing)
        self._from_email.setEnabled(not processing)
        self._preview_button.setEnabled(not processing)

        if processing:
            self._set_excel_controls_enabled(False)
            self._set_to_column_enabled(False)
        else:
            self._apply_dependent_enable_state()

        self._update_process_state()

    def _build_run_config(self) -> RunConfig | None:
        try:
            return build_run_config_from_inputs(
                template_path=self._template_path.text(),
                excel_path=self._excel_path.text(),
                to_column_key=self._selected_to_column_key(),
                from_email=self._from_email.text(),
                tenant_id=self._tenant_id.text(),
                client_id=self._client_id.text(),
                client_secret=self._client_secret.text(),
                subject_template=self._subject_template.text(),
                save_to_sent=True,
                dry_run=False,
            )
        except MailMergeError as exc:
            self._show_error_dialog("Invalid configuration", str(exc))
            return None

    def _build_preview_config(self) -> RunConfig | None:
        to_column_key = self._selected_to_column_key()
        if not to_column_key:
            self._show_error_dialog(
                "Preview unavailable",
                "Select a recipient column before previewing.",
            )
            return None
        from_email = self._from_email.text()
        if from_email and not is_from_email_valid(from_email):
            from_email = ""
        try:
            return build_run_config_from_inputs(
                template_path=self._template_path.text(),
                excel_path=self._excel_path.text(),
                to_column_key=to_column_key,
                from_email=from_email,
                tenant_id="",
                client_id="",
                client_secret="",
                subject_template=self._subject_template.text(),
                save_to_sent=False,
                dry_run=True,
            )
        except MailMergeError as exc:
            self._show_error_dialog("Invalid configuration", str(exc))
            return None

    def _start_run(self, config: RunConfig) -> None:
        self._set_processing(True)
        self._cancel_event = threading.Event()

        self._progress_dialog = QProgressDialog(
            "Preparing mail merge...",
            "Cancel",
            0,
            0,
            self,
        )
        self._progress_dialog.setWindowTitle("Processing")
        self._progress_dialog.setWindowModality(Qt.WindowModal)
        self._progress_dialog.setAutoClose(False)
        self._progress_dialog.setAutoReset(False)
        self._progress_dialog.canceled.connect(self._on_progress_canceled)
        self._progress_dialog.show()

        worker = _RunWorker(config, self._cancel_event)
        worker.signals.progress.connect(self._on_run_progress)
        worker.signals.error.connect(self._on_run_error)
        worker.signals.finished.connect(self._on_run_finished)
        self._thread_pool.start(worker)

    def _on_preview_clicked(self) -> None:
        if self._processing:
            return
        if self._template_info is None or self._sheet_info is None:
            self._show_error_dialog(
                "Preview unavailable",
                "Load a template and spreadsheet before previewing.",
            )
            return
        if not self._loaded_rows:
            self._show_error_dialog(
                "Preview unavailable",
                "Spreadsheet contains no rows to preview.",
            )
            return
        config = self._build_preview_config()
        if config is None:
            return
        dialog = PreviewDialog(
            config=config,
            template_info=self._template_info,
            sheet_info=self._sheet_info,
            rows=self._loaded_rows,
            parent=self,
        )
        dialog.exec()

    def _on_process_clicked(self) -> None:
        if self._processing:
            return
        config = self._build_run_config()
        if config is None:
            return
        self._start_run(config)

    def _on_progress_canceled(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
        if self._progress_dialog is not None:
            self._progress_dialog.setLabelText("Cancelling...")

    def _on_run_progress(self, event: ProgressEvent) -> None:
        if self._progress_dialog is None:
            return
        if self._progress_dialog.maximum() != event.total:
            self._progress_dialog.setMaximum(event.total)
        self._progress_dialog.setValue(event.processed)
        self._progress_dialog.setLabelText(
            f"Processing row {event.row_index} ({event.processed}/{event.total})"
        )
        self.statusBar().showMessage(
            f"Processed {event.processed} of {event.total} rows.",
        )

    def _on_run_error(self, message: str) -> None:
        self._finish_run()
        self._show_error_dialog("Run failed", message)

    def _on_run_finished(self, summary: RunSummary) -> None:
        cancelled = bool(self._cancel_event and self._cancel_event.is_set())
        self._finish_run()
        self._show_summary_dialog(summary, cancelled)

    def _finish_run(self) -> None:
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None
        self._cancel_event = None
        self._set_processing(False)

    def _show_summary_dialog(self, summary: RunSummary, cancelled: bool) -> None:
        message_lines = []
        if cancelled and summary.processed_rows < summary.total_rows:
            message_lines.append("Run cancelled.")
        message_lines.append(
            f"Processed {summary.processed_rows} of {summary.total_rows} rows."
        )
        message_lines.append(f"Successes: {summary.success_count}")
        message_lines.append(f"Failures: {summary.failure_count}")

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Run summary")
        dialog.setIcon(QMessageBox.Information)
        dialog.setText("\n".join(message_lines))

        failure_details = self._format_failure_details(summary)
        if failure_details:
            dialog.setDetailedText(failure_details)
        dialog.exec()

    def _format_failure_details(self, summary: RunSummary) -> str:
        failures: list[str] = []
        for result in summary.results:
            if result.success:
                continue
            error_text = str(result.error) if result.error else "Unknown error"
            failures.append(f"Row {result.row.row_index}: {error_text}")
        return "\n".join(failures)

    def _show_template_warning_dialog(self, warnings: list[str]) -> None:
        if not warnings:
            return
        self._dismiss_template_warning_dialog()
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Template warnings")
        dialog.setIcon(QMessageBox.Warning)
        dialog.setText("\n".join(warnings))
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.setModal(False)
        dialog.finished.connect(self._on_template_warning_dialog_finished)
        self._template_warning_dialog = dialog
        dialog.open()

    def _on_template_warning_dialog_finished(self, _result: int) -> None:
        dialog = self._template_warning_dialog
        self._template_warning_dialog = None
        if dialog is not None:
            dialog.deleteLater()

    def _show_error_dialog(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)
