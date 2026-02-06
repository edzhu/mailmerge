# mailmerge (Python)

## Table of contents
- [Overview / purpose](#overview--purpose)
- [Key features](#key-features)
- [High-level design](#high-level-design)
- [Install & setup](#install--setup)
- [Usage](#usage)
- [Microsoft 365/Outlook (Graph) credentials setup](#microsoft-365outlook-graph-credentials-setup)
- [Testing](#testing)
- [Packaging/building executables](#packagingbuilding-executables)
- [Security notes](#security-notes)

## Overview / purpose
mailmerge is a Python desktop mail-merge emailer that combines a Word `.docx` template
(MERGEFIELD fields or `«token»` placeholders) with an Excel `.xlsx` workbook, renders
each merged document to HTML, and sends email through Microsoft Graph. The core pipeline
uses `lxml` to parse Word XML, `openpyxl` to read spreadsheets, `mammoth` to convert DOCX
to HTML, and `msal` + `requests` for Graph authentication and API calls. A PySide6 GUI
wraps the workflow; the CLI entry point is currently a dry-run scaffold unless `--gui`
is supplied.

## Key features
- Template analysis and validation for MERGEFIELD and `«token»` placeholders.
- Excel header matching and row loading, with heuristics to suggest recipient columns.
- DOCX merge engine plus subject templating (tokens use `{Column}` syntax).
- HTML renderer that produces Outlook-friendly HTML using `mammoth`.
- Microsoft Graph client with token caching, retries, and explicit timeouts.
- GUI workflow with background workers, preview rendering, progress/cancel support, and
  run artifacts (`run.log`, `audit.jsonl`, `results.csv`).
- Optional rich HTML preview when the QtWebEngine extra is installed.

## High-level design
Core logic lives under `mailmerge.core` and stays UI-agnostic:

- `template_analyzer.analyze_template` inspects `.docx` files for merge fields.
- `excel_loader.load_matching_sheet` loads `.xlsx` data and finds a matching header row.
- `merge_engine.merge_docx_bytes` replaces merge fields in the DOCX payload.
- `html_renderer.docx_bytes_to_html` converts merged DOCX to HTML via `mammoth`.
- `text_templating.render_subject` replaces `{Field}` tokens in subject templates.
- `graph_client.GraphClient` authenticates with MSAL and calls Graph `/sendMail`.
- `run_controller.RunController` orchestrates the workflow; `reporting.write_results_csv`
  and `logging_setup.AuditWriter` produce run artifacts.

The GUI lives under `mailmerge.ui`:

- `main_window.MainWindow` wires UI inputs to the controller, runs background workers,
  and launches `preview_dialog.PreviewDialog` for dry-run rendering.

For more detail, see [docs/design.md](docs/design.md).

## Install & setup
Prerequisites: Python 3.9+ (3.11 recommended).

### macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -e ".[gui]"     # PySide6 GUI
pip install -e ".[preview]" # optional QtWebEngine HTML preview
```

### Windows (PowerShell)
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install -e ".[gui]"
pip install -e ".[preview]"
```

Optional extras:
- `.[test]` for pytest
- `.[build]` for PyInstaller

Development guidelines: see [docs/python_coding_guideline.md](docs/python_coding_guideline.md).

## Usage
### CLI (dry-run scaffold)
```bash
python -m mailmerge.main
# or, after installation:
mailmerge
```
This prints a status message and exits. Use `--gui` to launch the desktop app.

### GUI workflow
```bash
python -m mailmerge.main --gui
# or:
mailmerge --gui
```

1. Select a Word `.docx` template containing MERGEFIELD fields or `«token»` placeholders.
2. Select an Excel `.xlsx` file with a header row matching the template fields.
3. Choose the recipient ("To") column suggested by the UI.
4. Enter a subject template (tokens use `{Column Header}` syntax, e.g. `{姓名}` or
   `{First Name}`).
5. Enter the sender address and Microsoft Graph credentials.
6. Click **Preview** to render a single row without sending, or **Process** to send all
   rows.

Each run creates a timestamped directory under `~/MailMergeRuns/` (your home directory)
with `run.log`, `audit.jsonl`, and `results.csv`.

## Microsoft 365/Outlook (Graph) credentials setup
The app uses the Microsoft Graph **client credentials** flow, which requires an app
registration with **application** permissions.

1. In the Microsoft Entra admin center (Azure portal), register a new application.
2. Copy the **Application (client) ID** and **Directory (tenant) ID**.
3. Create a **client secret** under *Certificates & secrets* and store it securely.
4. Add **Microsoft Graph → Application permissions → Mail.Send** and grant admin consent.
5. Ensure the `from_email` address is a mailbox in the tenant. For shared mailboxes,
   grant the sender appropriate *Send As* rights.

Use the tenant ID, client ID, and client secret in the GUI.

## Testing
```bash
pip install -e ".[test]"
pytest -q
```
Tests are designed to run offline without network calls.

## Packaging/building executables
Use the helper scripts to create a build venv and run PyInstaller:
- `scripts/build_macos.sh`
- `scripts/build_windows.ps1`

Manual build (both platforms):
```bash
pip install -e ".[build]"
pyinstaller --onefile --windowed --name UIApp src/mailmerge/main.py
```
The output executable appears in `dist/` (macOS) or `dist\UIApp.exe` (Windows).

## Security notes
- Treat the client secret as a password. Do not commit it or paste it into logs.
- Run artifacts include recipient addresses and subjects; store `MailMergeRuns/`
  in a protected location and delete runs you no longer need.
- The logging layer redacts fields named `client_secret`, but you should still keep
  credentials out of screenshots, terminals, and support bundles.
