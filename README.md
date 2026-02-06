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
Prerequisites:
- Python 3.9+ (3.11 recommended to match current development defaults).
- `pip` (bundled with Python).

### macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -e ".[gui]"     # PySide6 GUI
pip install -e ".[preview]" # optional QtWebEngine HTML preview
```
Skip the `preview` extra if you do not need the embedded HTML preview window.

### Windows (PowerShell)
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install -e '.[gui]'
pip install -e '.[preview]'
```
If PowerShell blocks activation, run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that shell and retry.

Optional extras:
- `.[test]` for pytest
- `.[build]` for PyInstaller

Development guidelines: see [docs/python_coding_guideline.md](docs/python_coding_guideline.md).

## Usage
### CLI (status-only scaffold)
```bash
mailmerge
python -m mailmerge.main
```
This prints a status message and exits. Use `--gui` to launch the desktop app.

### Launching the GUI
```bash
mailmerge --gui
# or, from a development checkout:
python -m mailmerge.main --gui
```

### GUI walkthrough
1. Select a Word `.docx` template. The app scans for MERGEFIELD codes and `«token»`
   placeholders and surfaces any template warnings.
2. Select an Excel `.xlsx` file. The loader scans worksheets in workbook order, finds the
   first sheet whose header row contains all required template fields (after
   canonicalization), and loads the rows beneath that header.
3. Choose the recipient ("To") column. Columns that look like email addresses are
   auto-suggested; if none are detected, the dropdown lists all columns and shows a
   warning.
4. Enter the **From** email address.
5. Enter the **Tenant ID**, **Client ID**, and **Client Secret** for Microsoft Graph.
6. Optionally adjust the subject template. Tokens use `{字段}` syntax, for example:
   `薪酬单 {年份}年{月份}月 - {姓名}`.
7. Click **Preview** to render a single row without sending, then click **Process** to send
   all rows.

### Outputs / artifacts
Each **Process** run creates a timestamped directory under `~/MailMergeRuns/` (e.g.,
`~/MailMergeRuns/20240206-153045`; a suffix like `-01` is added if the timestamp already
exists). The run folder typically contains:
- `run.log` — end-to-end log output (console + file).
- `audit.jsonl` — per-row audit events with timestamps and status.
- `results.csv` — summary of row outcomes (recipient, status, and optional
  subject/request IDs).

### Examples
**Subject template:** `薪酬单 {年份}年{月份}月 - {姓名}`

**Header/field matching (canonicalization):** fields and headers are normalized with
Unicode NFKC, guillemet removal, and removal of spaces (ASCII + full-width), underscores,
slashes, colons, hyphens, and em dashes. Examples:
- Word field `事假未到职` matches Excel header `事假/未到职`.
- Word field `备__注` matches Excel header `备  注`.

## Microsoft 365/Outlook (Graph) credentials setup
The app uses the Microsoft Graph **client credentials** flow, which requires an app
registration with **application** permissions.

Checklist:
1. In the Microsoft Entra admin center (Azure portal), create a new **App registration**.
2. Record the **Directory (tenant) ID** and **Application (client) ID**.
3. Under **Certificates & secrets**, create a **client secret** and copy the value.
4. Under **API permissions**, add **Microsoft Graph → Application permissions → Mail.Send**.
5. Click **Grant admin consent** for your tenant.
6. Confirm the **From** mailbox exists in the tenant (user or shared mailbox). If you use
   Exchange Online application access policies, allow this app to access the mailbox.

Use the tenant ID, client ID, and client secret in the GUI. For broader context on the
Graph flow and mailbox expectations, see [docs/design.md](docs/design.md).

## Testing
```bash
pip install -e ".[test]"
pytest -q
```
Tests are designed to run offline without network calls.

## Packaging/building executables
See [RELEASE.md](RELEASE.md) for the step-by-step macOS/Windows packaging guide and
artifact details.

## Security notes
- Do **not** commit tenant IDs, client IDs, or client secrets to source control. Treat the
  client secret like a password and rotate it if it is exposed.
- Run artifacts include recipient addresses and subjects; store `MailMergeRuns/`
  in a protected location and delete runs you no longer need.
- The logging layer redacts values for keys named `client_secret` (and common
  `client_secret=...` patterns), but you should still keep credentials out of
  screenshots, terminals, and support bundles.
