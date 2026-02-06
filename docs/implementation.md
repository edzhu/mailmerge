## LLM-ready implementation plan

### Phase 0 — Quick wins (UI defaults + progress text)

1. **Set the default subject template**

   * File: `src/app/ui/main_window.py`
   * In `MainWindow.__init__` (or `_prime_state` equivalent), set:

     * `self._subject_template.setText("薪酬单 {年份}年{月份}月 - {姓名}")`
   * Optional behavior: if user loads a template and subject field is empty, auto-fill default.

**Acceptance criteria**

* App launches with the subject pre-filled as the design default.
* Users can still override it.

2. **Show recipient in progress dialog**

   * File: `src/app/ui/main_window.py`
   * Update `_on_run_progress(self, event: ProgressEvent)` to include recipient:

     * Label like: `Processing row {row_index} for {recipient} ({processed}/{total})`
     * If `recipient` is empty/None: omit or show `(no recipient)`.

**Acceptance criteria**

* Progress dialog clearly displays who is currently being processed.

---

### Phase 1 — Wire run artifacts and CSV export into the run flow

3. **Write `results.csv` at the end of a run and store paths in `RunSummary`**

   * Files:

     * `src/app/core/run_controller.py`
     * `src/app/core/reporting.py` (likely unchanged)
     * `src/app/ui/main_window.py` (to display paths)

**Implementation steps**

* Extend `RunController.run(...)` to accept `run_dir: Path | None` (optional).

  * If provided, set it on the returned `RunSummary.run_dir`.
* After processing completes (or even on cancellation), call:

  * `results_csv_path = write_results_csv(run_dir, summary)`
  * then `summary = replace(summary, results_csv_path=results_csv_path)`
* In `_RunWorker.run()` (UI):

  * It already creates `run_dir = create_run_directory(None)`; pass it into `RunController.run(...)`.
  * Keep using `configure_logging(run_dir)` and `AuditWriter(run_dir)`.

4. **Show artifact locations in the final summary dialog**

   * File: `src/app/ui/main_window.py`
   * In `_show_summary_dialog(...)`, add lines like:

     * `Run folder: <path>`
     * `Results CSV: <path>`
   * Optional (nice UX): add a button “Open run folder” (platform-dependent; can be skipped for v1).

**Acceptance criteria**

* Each run produces `MailMergeRuns/<timestamp>/results.csv`.
* `RunSummary.run_dir` and `RunSummary.results_csv_path` are set.
* UI displays where outputs are stored.

---

### Phase 2 — Add Graph request IDs into results and audit

5. **Capture Graph request identifiers**

   * File: `src/app/core/graph_client.py`
   * Modify `send_mail(...)` to return a dict that includes:

     * `request_id` (from response header `request-id` if present)
     * `client_request_id` (if you set one; optional)
     * `status_code`
     * (keep existing parsed JSON body if useful)

**Implementation detail**

* In `_request_with_retry`, preserve the final `requests.Response`.
* In `send_mail`, after success:

  * read headers like:

    * `request-id`
    * `client-request-id`
    * `x-ms-ags-diagnostic` (optional but can help debugging)
  * return them in the mapping.

6. **Record request id in audit events and row results**

   * File: `src/app/core/run_controller.py`
   * Thread the returned metadata from `graph_client.send_mail(...)` into:

     * `RowResult` (either add a new field, or stash into error/message)
     * `_write_audit_event(...)` payload as `graph_request_id` / `graph_client_request_id`

**Acceptance criteria**

* `audit.jsonl` includes a request id for successful sends (and possibly for failures where a response exists).
* If request id is present, it’s easy to correlate with tenant logs/support.

---

### Phase 3 — Robust MERGEFIELD replacement (beyond visible `«…»` tokens)

7. **Replace MERGEFIELD complex field results**

   * File: `src/app/core/merge_engine.py`

**Approach (practical v1):**

* Keep existing token replacement (works for many templates).
* Add a second pass that walks each paragraph’s run sequence and recognizes complex fields:

  * Identify `w:fldChar` with `w:fldCharType="begin"`
  * Collect `w:instrText` nodes until `w:fldCharType="separate"`
  * Parse MERGEFIELD name + format switch from the collected instr text
  * From `separate` until `w:fldCharType="end"`, replace any `w:t` nodes with the merged value (usually first `w:t` is enough; clear the rest)

**Key points**

* Use the same canonicalization used elsewhere.
* Apply `FieldInfo.format_hint` where possible (already supported by `format_value`).
* Ensure you do not break non-merge fields (only act on instr text containing `MERGEFIELD`).

8. **Add/extend tests**

   * Files: `tests/test_renderer.py`, `tests/test_errors.py`, or add a new test `tests/test_merge_engine_mergefield.py`
   * Add a minimal synthetic `document.xml` fixture representing a complex MERGEFIELD and validate it gets replaced even if no `«…»` appears.

**Acceptance criteria**

* Templates using genuine Word MERGEFIELDs merge correctly even if the visible guillemet token text isn’t present the way the current replacer expects.

---

### Phase 4 — Retry jitter + slightly safer defaults

9. **Add jitter to retry backoff**

   * File: `src/app/core/graph_client.py`
   * In `_retry_delay_seconds`, apply jitter:

     * `delay = base * (2**attempt)`
     * `delay *= random.uniform(0.8, 1.2)` (example)
   * Keep honoring `Retry-After` when present (no jitter needed there).

10. **Consider tuning defaults**

* Keep conservative but more robust, e.g.:

  * `_DEFAULT_MAX_RETRIES = 4` (still not excessive)
* Ensure tests remain deterministic (inject RNG or allow disabling jitter in tests via injected function).

**Acceptance criteria**

* Retries remain correct for 429/5xx, with non-identical delays under repeated errors.
* Tests pass deterministically.

---
