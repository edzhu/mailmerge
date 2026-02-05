"""Main window for the PySide6 GUI."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    """Main window for the mail-merge emailer GUI."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mail-merge emailer")

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
        self._to_column.addItems(["", "Email", "To", "Recipient"])

        self._subject_template = QLineEdit()
        self._subject_template.setPlaceholderText("Subject template")

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

    def _picker_row(self, line_edit: QLineEdit, button: QPushButton) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        layout.addWidget(button)
        return row

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

    def _on_preview_clicked(self) -> None:
        self.statusBar().showMessage("Preview not yet implemented.", 5000)

    def _on_process_clicked(self) -> None:
        self.statusBar().showMessage("Processing not yet implemented.", 5000)
