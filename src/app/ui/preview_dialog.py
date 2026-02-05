"""Preview dialog for rendering dry-run mail merge output."""

from __future__ import annotations

from html import escape
from typing import Callable, Sequence

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.core.canonicalize import canonicalize
from app.core.models import RowData, RowResult, SheetInfo, TemplateInfo
from app.core.run_controller import RunConfig, RunController
from app.ui.preview_logic import apply_preview_result_to_viewer
from app.ui.worker import ControllerWorker

_IDENTIFIER_LABELS = ("序号", "姓名")


class PreviewDialog(QDialog):
    """Dialog for rendering a selected row without sending email."""

    def __init__(
        self,
        *,
        config: RunConfig,
        sheet_info: SheetInfo,
        template_info: TemplateInfo,
        rows: Sequence[RowData],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preview")
        self.resize(960, 700)

        self._config = config
        self._sheet_info = sheet_info
        self._template_info = template_info
        self._rows = list(rows)

        self._thread_pool = QThreadPool.globalInstance()
        self._identifier_keys = self._resolve_identifier_keys()

        self._row_selector, self._selector_is_combo = self._build_row_selector()
        self._render_button = QPushButton("Render")
        self._render_button.clicked.connect(self._on_render_clicked)

        self._subject_value = QLabel("")
        self._subject_value.setWordWrap(True)
        self._subject_value.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self._html_view, self._html_setter = self._create_html_view()

        self._build_layout()
        self._prime_state()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)

        row_layout = QHBoxLayout()
        row_layout.addWidget(QLabel("Row"))
        row_layout.addWidget(self._row_selector)
        row_layout.addStretch(1)
        row_layout.addWidget(self._render_button)
        layout.addLayout(row_layout)

        subject_layout = QFormLayout()
        subject_layout.addRow("Subject", self._subject_value)
        layout.addLayout(subject_layout)

        layout.addWidget(self._html_view, 1)

    def _prime_state(self) -> None:
        if not self._rows:
            self._render_button.setEnabled(False)
            self._row_selector.setEnabled(False)
            self._subject_value.setText("No rows available.")
            self._set_html(self._empty_html("No rows loaded."))
            return
        self._set_html(self._empty_html("Select a row and click Render."))

    def _resolve_identifier_keys(self) -> list[tuple[str, str]]:
        keys: list[tuple[str, str]] = []
        for label in _IDENTIFIER_LABELS:
            key = canonicalize(label)
            if key and key in self._sheet_info.columns_by_key:
                keys.append((label, key))
        return keys

    def _build_row_selector(self) -> tuple[QComboBox | QSpinBox, bool]:
        if self._identifier_keys:
            selector = QComboBox()
            if self._rows:
                for index, row in enumerate(self._rows):
                    selector.addItem(self._format_row_label(index, row), index)
            else:
                selector.addItem("No rows", None)
                selector.setEnabled(False)
            return selector, True

        selector = QSpinBox()
        if self._rows:
            selector.setMinimum(1)
            selector.setMaximum(len(self._rows))
            selector.setValue(1)
        else:
            selector.setMinimum(1)
            selector.setMaximum(1)
            selector.setValue(1)
            selector.setEnabled(False)
        return selector, False

    def _format_row_label(self, list_index: int, row: RowData) -> str:
        details: list[str] = []
        for label, key in self._identifier_keys:
            value = row.values_by_key.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                value_text = value.strip()
                if not value_text:
                    continue
            else:
                value_text = str(value)
            details.append(f"{label}: {value_text}")
        base = f"Row {list_index + 1}"
        if details:
            return f"{base} - " + " / ".join(details)
        return base

    def _selected_row(self) -> RowData | None:
        if not self._rows:
            return None
        if self._selector_is_combo:
            data = self._row_selector.currentData()
            index = int(data) if data is not None else self._row_selector.currentIndex()
        else:
            index = self._row_selector.value() - 1
        if 0 <= index < len(self._rows):
            return self._rows[index]
        return None

    def _on_render_clicked(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.warning(self, "Preview", "Select a row to render.")
            return
        self._set_rendering(True)

        worker = ControllerWorker(self._render_preview, row)
        worker.signals.result.connect(self._on_render_result)
        worker.signals.error.connect(self._on_render_error)
        worker.signals.finished.connect(self._on_render_finished)
        self._thread_pool.start(worker)

    def _render_preview(self, row: RowData) -> RowResult:
        controller = RunController()
        return controller.preview_row(
            config=self._config,
            row=row,
            template_info=self._template_info,
        )

    def _on_render_result(self, result: RowResult) -> None:
        apply_preview_result_to_viewer(
            result,
            set_subject=self._subject_value.setText,
            set_html=self._set_html,
            empty_html=self._empty_html,
        )
        if not result.success:
            message = str(result.error) if result.error else "Preview failed."
            QMessageBox.warning(self, "Preview error", message)

    def _on_render_error(self, message: str) -> None:
        self._subject_value.setText("")
        self._set_html(self._empty_html("Preview failed."))
        QMessageBox.warning(self, "Preview error", message)

    def _on_render_finished(self) -> None:
        self._set_rendering(False)

    def _set_rendering(self, rendering: bool) -> None:
        self._render_button.setEnabled(not rendering)
        if self._rows:
            self._row_selector.setEnabled(not rendering)

    def _create_html_view(self) -> tuple[QWidget, Callable[[str], None]]:
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except (ModuleNotFoundError, ImportError):
            view = QTextBrowser()
            view.setOpenExternalLinks(True)
            return view, view.setHtml
        view = QWebEngineView()
        return view, view.setHtml

    def _set_html(self, html: str) -> None:
        self._html_setter(html)

    def _empty_html(self, message: str) -> str:
        safe_message = escape(message)
        return (
            "<!doctype html>\n"
            "<html>\n"
            "<head>\n"
            "<meta charset=\"utf-8\">\n"
            "<style>\n"
            "body {\n"
            "  font-family: \"Microsoft YaHei\", \"PingFang SC\", "
            "\"Noto Sans CJK SC\", Arial, sans-serif;\n"
            "  font-size: 14px;\n"
            "  padding: 12px;\n"
            "}\n"
            "</style>\n"
            "</head>\n"
            "<body>\n"
            f"<p>{safe_message}</p>\n"
            "</body>\n"
            "</html>\n"
        )
