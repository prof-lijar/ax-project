# Background workers

`weekly_report.py` is the independently scalable, durable execution boundary
for high-volume weekly-report exports. PostgreSQL leases coordinate a single
paged producer, bounded asynchronous consumers, and a recoverable finalizer.
Workers can be replicated on hosts that share the job database and private
artifact volume.

Each worker process admits up to `WEEKLY_REPORT_ACTIVE_JOB_LIMIT` distinct jobs
(four by default), so a newly submitted job does not wait for an earlier job to
finish. `WEEKLY_REPORT_WORKER_CONCURRENCY` remains one shared process-wide limit
across those jobs; adding active jobs does not multiply simultaneous report or
model calls.

The worker does not expose an HTTP port, schedule jobs, or send Slack messages.
`apps/weekly_report_bulk_api` is the separate private operator control plane for
submission, content-free status, cancellation, and verified export download.
The default development UI reaches that API through the Vite proxy. See the
weekly-report implementation specification for UI and CLI operation, cleanup,
capacity evaluation, and remaining benchmark gates.

## Generate weekly reports and save to the database

Date: 2026-09-09

Run these commands from the `nexgent/` repository root with the Compose stack
running. Terminal submissions save generated reports to the report database
by default; no `--write` flag is needed. UI test submissions produce ZIP
exports without report-table writes. Existing subscriber/week reports are
updated on conflict.

Submit up to 10,000 reports for a completed week (replace the example Monday
and idempotency key for another week):

```bash
docker compose exec weekly-report-worker \
  uv run python -m apps.workers.weekly_report submit \
  --week-start 2026-08-31 \
  --timezone Asia/Seoul \
  --max-reports 10000 \
  --idempotency-key terminal-db-all-20260831-20260909-01
```

The running worker automatically processes the job. To test with 100 reports,
use `--max-reports 100` and a distinct idempotency key. Reusing a key returns
the existing job; it does not start a fresh run.

Copy the returned `job_id` to check progress:

```bash
docker compose exec weekly-report-worker \
  uv run python -m apps.workers.weekly_report status <job_id>
```

For the full run submitted on September 9:

```bash
docker compose exec weekly-report-worker \
  uv run python -m apps.workers.weekly_report status \
  6736defc-fc11-4fc3-8ef3-680797fa7f38
```

`completed` means generation and report storage succeeded for the selected
reports. `partial` or `failed` requires inspecting the counts and worker logs.
The report count may be smaller than requested if fewer eligible subscribers
exist. To confirm all source pages were processed, check `producer_done: true`,
`selection_truncated: false`, and `next_cursor: null`; review warnings for
skipped source data. If `selection_truncated` is true, submit the same week
with `--cursor '<next_cursor>'` and a new idempotency key to process the next
batch, repeating until there is no continuation cursor.

Commands were checked against the CLI parser and Compose service definition.
The named job was accepted by the live bulk API with `persist_reports: true`;
its last observed status at submission was `pending`. Completion and database
contents have not been verified. Docker CLI execution requires an account
with Docker access. See [UI export/storage behavior and validation](../../../docs/08-implementation/weekly-reporter-ui-zip-only.md).

## Keep only the five latest ZIP exports

Date: 2026-09-09

The worker keeps the five most recently finished ZIP exports automatically.
To clean existing older ZIPs immediately after deploying the updated worker,
run from the repository root:

```bash
docker compose exec weekly-report-worker \
  uv run python -m apps.workers.weekly_report cleanup-exports
```

This deletes older ZIP files and clears their download links. Saved reports
in the database, report recovery artifacts, and run history are preserved.
Active jobs are excluded. See [retention behavior, deployment, and validation](../../../docs/08-implementation/weekly-report-five-zip-retention.md).
