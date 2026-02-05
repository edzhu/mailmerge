# Python Mail‑Merge Emailer (Office 365 / Outlook) — Design Document

**Document version:** 1.0  
**Last updated:** 2026‑02‑05  
**Target OS:** Windows (EXE) + macOS (APP)

---

## 1. Overview

This application is a **Python-based desktop executable** that provides Microsoft mail‑merge‑like functionality to send **HTML emails** via **Office 365 Outlook (Microsoft Graph)**.

On startup, the app presents a simple UI that lets the user:
1. Select a **Microsoft Word template (.docx)** containing templated fields (mail‑merge fields).
2. Select a **Microsoft Excel spreadsheet (.xlsx)** containing per-recipient values for those fields.
3. Choose a **“To Email Address” column** from a dropdown populated via an email‑column heuristic.
4. Enter a **From** email address.
5. Enter **Microsoft application credentials** (Tenant ID, Client ID, Client Secret) for Graph API access.

When the user clicks **Process**, the app merges the template with **each row** in the spreadsheet and sends **one HTML email per row** to the selected “To Email Address”.

This design is updated to explicitly support the prototype documents:
- **Word template:** `薪酬单.docx`
- **Excel data:** `工资条.xlsx`

Both are Chinese-language documents; the design ensures **full Unicode / Chinese support** throughout parsing, validation, merging, rendering, and sending.

---

## 2. Goals and non‑goals

### 2.1 Goals
- “Mail‑merge” style field replacement using a Word template and Excel rows.
- Robust field detection for Word mail‑merge fields, including visible tokens like `«字段»`.
- Robust header matching for Chinese spreadsheets (punctuation/spaces/underscores differences).
- Intuitive UI with **dependency-driven** enable/disable behavior.
- Send HTML emails through Office 365 using **Microsoft Graph** with **client credentials**.
- Provide clear run progress, per-row errors, and a final summary.
- Build **native executables** for Windows and macOS.

### 2.2 Non‑goals (v1)
- Interactive delegated sign-in (OAuth delegated flow).
- Attachments, inline images, or embedded files.
- Complex Word content types (e.g., floating text boxes, SmartArt) with perfect HTML fidelity.
- Persisting secrets or credentials to disk by default.

---

## 3. Prototype analysis and requirements (reference behavior)

### 3.1 Word template fields (prototype)
`薪酬单.docx` contains **28** merge fields. In the document body, these appear as guillemet tokens (e.g., `«姓名»`) and are also present as actual MERGEFIELD codes.

**Field list (unique names):**
- 序号, 部门, 入职时间, 姓名, 年份, 月份
- 当月应出勤天数, 事假未到职, 病假, 年假其他, 实际出出勤天数
- 标准工资, 岗位工资, 工资小计, 绩效奖, 奖金, 提成, 其他, 扣缺勤, 工资合计
- 社保, 住房公积金, 其他扣款, 合计
- 应发金额, 个税, 实发金额, 备__注

**Formatting hint in the template (prototype):**
Many money-related fields include Word numeric format switches like `\# "0.00"` in the merge field code. v1 should support a reasonable default:
- If a field code indicates a numeric format, apply that format when rendering the merged value (see §8.5).

### 3.2 Excel sheet and header row (prototype)
`工资条12‑KCL.xlsx` contains multiple sheets. Prototype behavior:
- **Sheet2** has summary columns like `求和项:工资合计` and does **not** contain all required fields.
- **Sheet1** is the row-level data sheet and contains a header row with all required fields (plus extra columns like `职务` and `邮箱`).

**Sheet1 header (first row) includes:**
年份, 月份, 序号, 部门, 姓名, 职务, 入职时间, 当月应出勤天数, 事假/未到职, 病假, 年假/其他, 实际出出勤天数, 标准工资, 岗位工资, 工资小计, 绩效奖, 奖金, 提成, 其他, 扣缺勤, 工资合计, 社保, 住房公积金, 其他扣款, 合计, 应发金额, 个税, 实发金额, 备  注, 邮箱

### 3.3 Prototype-specific header/field mismatches
The Word template uses field names without certain punctuation, while the spreadsheet uses human-friendly labels with punctuation/spaces:
- Excel `事假/未到职` ↔ Word `事假未到职`
- Excel `年假/其他` ↔ Word `年假其他`
- Excel `备  注` ↔ Word `备__注`

Therefore, **canonicalization/normalization** is required for matching.

---

## 4. User experience (UI)

### 4.1 Primary screen fields
1. **Word Template (.docx)** — file picker
2. **Excel File (.xlsx)** — file picker
3. **To Email Address column** — dropdown
4. **From Email Address** — text field
5. **Tenant ID** — text field
6. **Client ID** — text field
7. **Client Secret** — password field (masked)
8. (Recommended) **Email Subject template** — text field (optional)
   - Default: `薪酬单 {年份}年{月份}月 - {姓名}` (tokens refer to merge fields)

Buttons:
- **Process**
- **Preview** (optional but recommended)
- **Exit**

### 4.2 Dependency-driven enable/disable rules
- Excel picker disabled until Word template validates.
- To-column dropdown disabled until Excel validates.
- Process disabled until:
  - Word template valid
  - Excel valid and row data is present
  - A valid To-column is selected
  - From email is valid
  - Credentials yield a token (validated on Process or via “Test Login”)
- Any upstream invalidation clears dependent selections to prevent stale state.

### 4.3 Preview (recommended)
A Preview panel lets the user:
- Select a row index (or pick by 姓名/序号)
- Render merged HTML and display it in an embedded viewer
- Confirm formatting before sending

---

## 5. Field detection and validation (Word)

### 5.1 Supported field syntaxes
The template is considered valid if at least one field is found using any of:
1. **Word MERGEFIELD codes** (from `word/document.xml` instruction text)
2. **Visible token placeholders** in the text such as `«字段名»`

### 5.2 Extraction algorithm (docx)
Implementation:
- Open `.docx` as ZIP.
- Parse `word/document.xml` using an XML parser.
- Collect merge fields:
  - From `w:instrText` using regex that captures `MERGEFIELD ...`
  - From text nodes by scanning for `«...»`
- Deduplicate on exact field name; keep ordering for UI display.

### 5.3 Field metadata (optional enhancement)
While extracting, also capture:
- Whether a field has a numeric format switch (e.g., `\# "0.00"`).
- Store as `{ field_name -> format_hint }` for use during value formatting.

### 5.4 Validation rules
- **No fields found** → error dialog and template invalid.
- **Field names empty or malformed** → ignore and warn (does not fail unless all are malformed).

---

## 6. Excel parsing, sheet selection, and validation

### 6.1 Canonicalization (critical for Chinese)
The app matches Word fields to Excel headers using a **canonical key**.

**Canonicalize(name):**
1. Unicode normalize `NFKC`
2. Strip whitespace
3. Remove wrappers `« »` if present
4. Remove characters anywhere: spaces (ASCII + full-width), `_`, `/`, `\`, `:`, `：`, `-`, `—`
5. Collapse remaining whitespace to none

Examples:
- `事假/未到职` → `事假未到职`
- `年假/其他` → `年假其他`
- `备  注` → `备注`
- `备__注` → `备注`

### 6.2 Sheet selection algorithm
For each sheet in workbook order:
1. Find the **first non-empty row** (scan first 50 rows by default).
2. Treat that row as a header candidate.
3. Canonicalize each header cell to a key set.
4. If header key set contains **all template field keys**, select this sheet and header row.

If no sheet matches:
- Error dialog: “No sheet contains all required template fields.”

**Prototype note:** Even if the workbook lists `Sheet2` first, it will be rejected because it does not contain all required template fields; the algorithm selects `Sheet1`.

### 6.3 Data row extraction
- Data begins immediately after header row.
- For each row:
  - Build a dict of `{ canonical_header_key: value }`
  - Preserve also `{ original_header: value }` for reporting/export

Stop condition:
- Read through `max_row` and skip rows that are entirely empty.

### 6.4 Validation rules
- Word template fields (by canonical key) must all be present in the selected sheet header.
- Extra columns are allowed.
- If zero data rows are found → error dialog: “No data rows found.”

---

## 7. “To Email Address” column detection

### 7.1 Heuristic
The To-column dropdown is populated by scanning each column:
- Sample up to **K rows** (default 50).
- Count cells matching a conservative email regex:
  `^[^@\s]+@[^@\s]+\.[^@\s]+$`
- If match ratio ≥ **0.6** and at least 3 matches → treat as email column.

### 7.2 Fallback behavior
If no columns qualify:
- Show all columns with a warning: “No column strongly resembles email addresses.”

**Prototype expectation:** `邮箱` will qualify and appear in the dropdown.

---

## 8. Merge, formatting, and HTML rendering

### 8.1 Merge semantics
For each spreadsheet row:
- For every template field:
  - Lookup by canonical key
  - Substitute value into the merged Word document

Missing cell values:
- Default to empty string (`""`) unless configured as “required” (future option).

### 8.2 Value formatting (general)
- Dates/times:
  - If Excel cell is a datetime → format as `YYYY-MM-DD` by default
- Numbers:
  - Integer-like floats → render as integer (e.g., `23.0` → `23`)
  - Currency/money → two decimals by default (configurable)
- Strings:
  - Preserve Chinese characters; trim trailing whitespace

### 8.3 Word numeric format switches (prototype-aware)
If the Word merge field code contains a numeric format switch like `\# "0.00"`:
- Prefer that as the rendering format for that field.
- v1 supports a small set:
  - `0.00` (two decimals)
  - `0` (no decimals)
Other formats can fallback to default money formatting.

### 8.4 HTML conversion
Convert merged `.docx` to HTML using a library such as **mammoth**.

Post-processing for email compatibility:
- Ensure `<meta charset="utf-8">` is present.
- Optionally inline simple styles (tables/borders) to improve Outlook rendering.
- Use a safe CJK font stack:
  `Microsoft YaHei, PingFang SC, Noto Sans CJK SC, Arial, sans-serif`

### 8.5 Output HTML constraints
Because Outlook desktop uses a Word-like rendering engine, keep HTML conservative:
- Prefer tables for layout (Word templates often are table-based).
- Avoid advanced CSS; keep to inline styles if used.

---

## 9. Email sending (Microsoft Graph)

### 9.1 Authentication
Use **client credentials flow** to obtain an access token from Microsoft identity platform:
- Requires Tenant ID, Client ID, Client Secret
- Scope: `https://graph.microsoft.com/.default`

Implementation can use:
- **MSAL for Python** (recommended) for token caching and retries, OR
- manual token endpoint call with `requests`

### 9.2 Sending mail endpoint
Send per-recipient email using:
- `POST /v1.0/users/{from_email}/sendMail`

Message content:
- `body.contentType = "HTML"`
- `body.content = <merged html>`

### 9.3 Permissions and policy notes
- App-only permission: `Mail.Send` (Application)
- Organization admins should restrict app mailbox access using application access policies where possible.

### 9.4 Throttling and retries
- Retry transient errors:
  - HTTP 429, 503, 502, 504
- Exponential backoff with jitter
- Do not retry on 4xx validation errors (except 429).

---

## 10. Processing workflow

For each row in the selected sheet:
1. Determine recipient email from chosen To-column.
   - If empty/invalid: record failure and continue.
2. Merge values into the Word template.
3. Convert merged docx to HTML.
4. Build subject (optional subject template using field tokens).
5. Send email via Graph.
6. Record result (success/failure, error message, timestamp).

UI shows:
- Progress counter (sent/total)
- Current recipient
- Cancel button (stops after current row finishes)

---

## 11. Logging, reporting, and audit

### 11.1 Run log
Write a structured run log file (JSONL recommended) containing per-row entries:
- row index / key identifiers (e.g., 序号, 姓名)
- recipient email
- send status
- Graph request id (if available)
- error message

### 11.2 Summary report
At completion show:
- Total rows
- Sent count
- Failed count
- Failures list with reason

Optional exports:
- CSV of results
- HTML preview of failed rows for troubleshooting

### 11.3 Sensitive data handling
- Never log Client Secret or access tokens.
- Mask secrets in UI.
- Do not persist credentials unless user explicitly opts in (future).

---

## 12. System architecture

### 12.1 Components
- **UI Layer** (PySide6 recommended)
- **TemplateAnalyzer**
  - Extract fields and format hints from docx XML
- **ExcelLoader**
  - Sheet/header detection, canonicalization, row dict creation
- **Merger**
  - Replace fields in a docx copy per row
- **Renderer**
  - docx → HTML conversion + post-processing for Outlook
- **GraphClient**
  - Token acquisition + sendMail calls + retry/backoff
- **RunController**
  - Orchestration, progress, cancellation, result aggregation
- **Logger/Reporter**

### 12.2 Data model (conceptual)
- `TemplateInfo`:
  - `fields: list[str]`
  - `field_key_map: dict[str, str]` (original -> canonical key)
  - `format_hints: dict[canonical_key, hint]`
- `SheetInfo`:
  - `sheet_name, header_row_index`
  - `columns: list[ColumnInfo]` (original header, canonical key, index)
- `RowData`:
  - `values_by_key: dict[canonical_key, Any]`
  - `values_by_header: dict[str, Any]`

---

## 13. Packaging and distribution

### 13.1 Build targets
- **Windows:** `PyInstaller --onefile` output `.exe`
- **macOS:** `PyInstaller` output `.app` bundle (optionally signed/notarized)

### 13.2 CI/CD
- Build on each OS runner.
- Attach artifacts to releases with checksums.
- Version embedding in the executable.

---

## 14. Testing strategy

### 14.1 Unit tests
- Word field extraction (MERGEFIELD + `«...»`) using prototype template.
- Canonicalization correctness for Chinese punctuation/spacing (prototype cases).
- Excel sheet selection correctly chooses Sheet1 over Sheet2.
- Email column heuristic correctly detects `邮箱`.
- Value formatting: dates, integers, currency.

### 14.2 Integration tests
- Mock Graph token + sendMail responses.
- Retry behavior on 429/5xx.

### 14.3 Manual acceptance
- Validate against the prototype files end-to-end:
  - Preview renders correct Chinese text
  - Emails sent successfully to sample recipients
  - Run summary and logs match expectations

---

## 15. Future enhancements
- Delegated OAuth flow (interactive login) to avoid client secrets.
- Attachments and inline images.
- Advanced HTML rendering/inlining for better Outlook fidelity.
- Rule-based per-field required/optional validation.
- Multi-template support and saved profiles (store mapping presets).

---

## Appendix A — Prototype canonical mapping examples
- `事假/未到职` → `事假未到职`
- `年假/其他` → `年假其他`
- `备  注` / `备__注` → `备注`
