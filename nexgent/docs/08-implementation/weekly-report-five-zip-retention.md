# Weekly Report Five-ZIP Retention

Date: 2026-09-09

## Implemented behavior

Weekly Reporter keeps at most five published ZIP exports per shared job
store/artifact volume, ordered by terminal job `updated_at` descending with
job ID as the tie breaker. This applies to UI and terminal runs shown on
`/agents/1`. Older run history remains visible, but its download reference is
cleared after its `weekly-reports.zip` file is deleted. The page states the
five-ZIP retention policy.

The worker runs cleanup at startup, every 30 seconds while serving jobs, and
after job execution. A one-shot `cleanup-exports` command applies the same
policy without generating reports or opening the report-table connection.
The existing age-based cleanup command remains available.

Only terminal jobs are cleanup candidates. New ZIPs being finalized are
protected until publication; the volume can temporarily exceed five ZIPs.
Unpublished ZIPs left by failed terminal jobs are also deleted. The sweep
preserves report database rows, source/output artifacts used for recovery,
job outcomes, and completion timestamps. It does not delete user-downloaded
copies or unrelated workflows' files.

Cleanup removes the ZIP before clearing its database reference. Filesystem
failures leave the reference eligible for retry; missing files are safe to
retry after a process crash. Cleanup failures are logged without changing a
successful generation/storage outcome. The periodic sweep retries them.
No database migration is required.

## Operations

Run from the repository root with Docker access. After the updated worker
image is deployed, manually clean old exports with:

```bash
docker compose exec weekly-report-worker \
  uv run python -m apps.workers.weekly_report cleanup-exports
```

The command prints `deleted_zip_count` and `retained_zip_limit: 5`.
Deploy when active generation has finished to avoid interrupting work:

```bash
docker compose up --build -d --no-deps weekly-report-worker frontend
```

The new worker automatically cleans existing old ZIPs on startup. Refresh
`http://192.168.0.18:5173/agents/1` to load the updated download references.

## Validation and remaining checks

Focused tests cover retaining five exports in completion order, deleting
failed-job orphan ZIPs, keeping active jobs/other workflows/report artifacts,
preserving completion timestamps, clearing download references, repeated
cleanup, a newly completed sixth export, failed-deletion retry, missing files,
and file-name traversal rejection. Existing runner and API tests are included.

Commands:

```bash
(cd agents && .venv/bin/pytest tests/unit/test_weekly_report_export_retention.py tests/unit/test_weekly_report_bulk.py tests/unit/test_bulk_artifacts.py tests/contract/test_weekly_report_bulk_api.py tests/contract/test_bulk_store_contract.py --disable-warnings)
(cd frontend && npm test && npm run build)
(cd frontend && CARGO_TARGET_DIR=/tmp/nexgent-cargo-ui-export cargo check --manifest-path src-tauri/Cargo.toml --offline)
```

All 216 frontend tests, the frontend build, and isolated offline Tauri check
passed. All 25 focused backend tests and changed-file Ruff checks passed;
`git diff --check` passed. The initial sandbox test run stalled with restricted
asyncio thread wakeups; tests were rerun outside the sandbox using fake data
and temporary artifacts.

Live cleanup and PostgreSQL execution are not verified: Docker access is denied
and `sudo -n docker compose ps --format json` requires interactive authentication.
No live ZIP deletion or deployment was performed. Run the deployment and
cleanup commands above with Docker access, verify only five published ZIPs
remain, and confirm older jobs no longer offer downloads. The npm audit remains
unverified from the earlier change: automatic review rejected the registry
request because it sends dependency metadata externally; it was not retried.
