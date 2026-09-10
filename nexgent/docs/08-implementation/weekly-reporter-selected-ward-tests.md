# Weekly Reporter Selected-Ward Test Runs

Date: 2026-09-09

## Implemented behavior

At `/agents/1`, the optional **Ward IDs** field accepts comma-separated positive
integer IDs, such as `23, 45 ,56`. Entering IDs fixes the report count to the
selection and disables the separate maximum-report control. Blank input retains
automatic selection. Invalid input blocks submission; it never falls back to
automatic discovery. Duplicate IDs, decimals, non-numeric tokens, empty comma
entries, and more than 25 IDs are rejected. The 25-ID limit matches the existing
explicit-selection source API contract.

The bulk request carries sorted `ward_ids` through the job store to the worker
and source API. The API normalizes `max_reports` to the number of selected IDs
and rejects combining an explicit selection with a cursor or report persistence.
All frontend submissions continue to send `persist_reports: false`. No report
rows are inserted or updated. Job metadata and private ZIP/recovery artifacts
still use the existing durable job and file stores.

The worker requests only the selected IDs, validates that source results stay
within that selection, and rejects unexpected continuation cursors. On restart,
it excludes already staged IDs before requesting the remainder. Missing wards
are warnings, without substitution or additional discovery. A run can therefore
complete with fewer reports than IDs requested. Source warnings can be expanded
on the page. The ZIP contains only generated selected-ward reports and records
the selection in its manifest. Existing five-ZIP retention still applies.

## Usage and rollout

1. Open `http://192.168.0.18:5173/agents/1`.
2. Choose the reporting week and enter `23, 45, 56` under **Ward IDs**.
3. Confirm the count is 3, approve the existing live-model checkbox, and click
   **Run Agent**.
4. When complete, choose **Download ZIP**. Expand source warnings if a requested
   ward could not be generated. Leave Ward IDs blank to return to bulk testing.

Deploy the new bulk API and worker contract together; an older API rejects the
new field. From the repository root, after active generation finishes:

```bash
docker compose up --build -d --no-deps weekly-report-bulk-api weekly-report-worker frontend
```

No database migration or source API change is required. Scheduled/ordinary
terminal runs continue using their existing database-saving behavior.

## Validation and limits

Validation uses mock source facts, a fake model, and a report writer that raises
if called. It covers exact selected IDs in ZIP content, missing wards without
replacement, unexpected source wards, resume from a partially staged selection,
API validation and persisted request fields, frontend parsing, count limits,
and the frontend request's disabled report persistence.

```bash
(cd agents && .venv/bin/pytest tests/unit/test_weekly_report_bulk.py tests/contract/test_weekly_report_bulk_api.py tests/unit/test_weekly_report_repository.py tests/unit/test_weekly_report_scheduler.py --disable-warnings)
(cd frontend && npm test && npm run build)
(cd frontend && CARGO_TARGET_DIR=/tmp/nexgent-cargo-ui-export cargo check --manifest-path src-tauri/Cargo.toml --offline)
```

All 230 frontend tests, TypeScript/Vite build, and isolated offline Tauri check
passed. All 43 focused backend tests, changed-file Ruff checks, and
`git diff --check` passed. Backend tests run outside the sandbox because its
asyncio thread wakeup restrictions caused hangs in earlier checks.

Live deployment and model-backed browser verification have not been performed;
Docker access in this session requires interactive administrator authentication.
Run the deployment command above, then follow the four usage steps and inspect
the ZIP: only available reports for 23, 45, and 56 should appear. Missing IDs
must not be replaced by another ward. The npm security audit remains unverified:
earlier automatic review blocked the registry request because it transmits
project dependency metadata externally; it was not retried.
