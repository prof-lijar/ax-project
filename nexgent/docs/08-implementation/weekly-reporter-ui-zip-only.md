# Weekly Reporter UI ZIP-only test runs

Date: 2026-09-09

## Behavior and decisions

New report-generation submissions from `/agents/1` always send
`persist_reports: false`. The worker creates the normal verified ZIP and
finishes the job without invoking the report-table writer. This removes the
report INSERT/UPSERT (including `created_at` handling) from UI test runs.
The page labels this action as test generation with ZIP-only output.
Use the existing **Download ZIP** action when generation finishes.

The ZIP contains `manifest.json`, `reports.jsonl`, per-ward Markdown in
`reports/`, and frontend JSON in `json/`. The manifest records the request's
persistence setting. Job tracking metadata remains in the bulk job database;
report artifacts remain on the private artifact volume for the existing
retention period. Source data is still read for generation.

The shared request contract defaults `persist_reports` to true to preserve
scheduled/CLI jobs and older queued jobs. The API persists the explicit false
value with the job, so it survives worker restarts. This change does not retry
or alter previously failed jobs; submit a new UI test after rollout.

## Validation

- 24 focused Python bulk runner, API, and scheduler tests passed.
- The export-only regression uses a report writer that raises on every call;
  generation completes and the ZIP passes integrity/content checks.
- The API regression confirms false survives request serialization/storage.
- All 216 frontend tests and the TypeScript/Vite production build passed.
- Ruff passed for all changed Python files.
- Tauri `cargo check` passed using an isolated offline target directory after
  the initial check encountered stale permission-cache paths from another checkout.
- `git diff --check` passed.
- npm audit could not reach the registry in the sandbox. Automatic approval
  review rejected the network retry because it transmits dependency metadata
  to npm; the security audit remains unverified.

Reproduce checks from the repository root:

```bash
(cd agents && .venv/bin/pytest tests/unit/test_weekly_report_bulk.py tests/contract/test_weekly_report_bulk_api.py tests/unit/test_weekly_report_scheduler.py)
(cd frontend && npm test && npm run build)
(cd frontend && CARGO_TARGET_DIR=/tmp/nexgent-cargo-ui-export cargo check --manifest-path src-tauri/Cargo.toml --offline)
(cd frontend && npm audit --audit-level=moderate)
```

## Rollout and remaining live verification

Docker socket access is denied for this account, so the live containers have
not been rebuilt. From the repository root, an operator with Docker access
must update both API and worker before testing the browser client:

```bash
docker compose up --build -d --no-deps weekly-report-bulk-api weekly-report-worker frontend
```

Open `http://192.168.0.18:5173/agents/1`, generate one test report, and select
**Download ZIP**. Confirm the submission and downloaded manifest contain
`persist_reports: false`, the job completes, and the ZIP contains its Markdown
and JSON report. A live model-backed browser run has not been performed.
