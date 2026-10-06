# Recover generated weekly reports into PostgreSQL

Date: 2026-09-08

The worker saves each completed report under its job's `reports/<ward_id>.json`
artifact before counting it as completed. It upserts the frontend report JSON
into `archive.resources_ward_weekly_report` only during finalization, after ZIP
creation and before marking the job terminal. An earlier failure or a database
transaction failure can therefore leave thousands of completed artifacts with
no report rows. A browser polling failure does not establish the cause of a
worker finalization failure.

Job `3b551881-d290-47f2-aec1-b23a90333dc1` was observed as failed with 6,436
completed reports, 128 of them fallback reports, four failed items, no active
items, and no registered export. The operator reported no rows in the target
table. Storage has not been executed by this assistant session because Docker
access requires interactive sudo authentication.

`apps/workers/recover_weekly_report_storage.py` is an operator recovery command.
It reads a consistent, read-only queue snapshot, requires a terminal unexpired
weekly-report job with no unfinished items and an exact expected count, then
verifies every completed report's path, checksum, schema, ward, and week.
Only report metadata and one report at a time are held in memory. It uses the
existing storage record mapper and atomic batched writer; no source or model
calls are made and no queue status or export metadata is changed.

From the `agents/` directory, validate the artifacts without writing:

```bash
sudo docker compose -f ../compose.yaml exec -T weekly-report-worker \
  uv run --no-sync python - 3b551881-d290-47f2-aec1-b23a90333dc1 \
  --expected-count 6436 < apps/workers/recover_weekly_report_storage.py
```

To store the verified reports:

```bash
sudo docker compose -f ../compose.yaml exec -T weekly-report-worker \
  uv run --no-sync python - 3b551881-d290-47f2-aec1-b23a90333dc1 \
  --expected-count 6436 --write < apps/workers/recover_weekly_report_storage.py
```

The script is streamed into the existing worker; no image rebuild or worker
restart is needed. It uses the container's configured artifact volume,
`WEEKLY_REPORT_JOB_DATABASE_DSN`, and `WEEKLY_REPORT_STORAGE_DATABASE_DSN`
(falling back to `ANSIMK_DATABASE_DSN` as in the normal writer). Secrets and
report content are not printed. Successful output includes `written_count: 6436`.

The existing writer uses one transaction in batches of 500 by default. Each
`(ward_id, week_start_date)` conflict updates that row, so retries do not create
duplicates; recovery replaces any existing report for those same ward/week keys.
The four failed items are not inserted. A validation or SQL failure within the
transaction rolls back all its batches. Terminal job state stays failed:
recovering table data does not claim that ZIP registration or all items succeeded.

Check the intended target database after success:

```sql
SELECT count(*) AS stored_reports
FROM archive.resources_ward_weekly_report
WHERE week_start_date = DATE '2026-08-31';
```

For an otherwise empty week, expect 6,436. Existing reports from other jobs for
the same week can make the count higher. If the command fails it returns the
exception class and SQLSTATE without connection credentials or raw report data.
For example, a missing table, conflicting schema, missing privileges, or an
unreachable database needs to be corrected before retrying; do not assume the
failure was caused by browser polling. The cause of the original finalization
failure remains unconfirmed until the worker logs or recovery error are checked.

Validation and limitations: unit tests cover completed-item selection, active
and expired job rejection, exact count, duplicate identity, checksum and week
verification, and dry-run versus write behavior. Existing bulk/storage tests
cover finalization failure and 6,001-report batching. Live recovery remains the
operator command above; no live database write has been claimed.

Verification results: nine recovery tests passed; the focused recovery,
existing bulk, and storage pass before CLI orchestration tests comprised 24
passing cases. The full suite then reported 369 passed, two skipped, and one
unrelated failure: `test_weekly_report_scheduler_image_fixes_cron_to_seoul_time`
expects the old Monday 03:00 cron in the concurrently edited scheduler.
Recovery-file Ruff, LangGraph validation (four graphs), Compose rendering,
weekly-reporter skill validation, and `git diff --check` passed. Whole-tree
Ruff reports two unrelated sort violations in the integrations exports and RAG
chat tests. Tests were rerun outside the sandbox after restricted asyncio thread
wakeups stalled execution. No unrelated files were changed to make checks pass.

## Selective recovery after NOT NULL errors (2026-09-08)

`--write --skip-not-null` tries each bounded batch inside a savepoint, then
retries failed batches row by row in savepoints, skipping only SQLSTATE 23502.
Valid rows commit together. Other SQL errors, artifact errors, and cancellation
still roll back the outer transaction. Regular bulk finalization and recovery
without this option retain their atomic policy.

Output includes `written_count`, `skipped_count`, `storage_status`, and `skipped`
entries with ward ID, column name, and SQLSTATE, without report data or raw
exception details. Exit code 2 means rows were skipped, even when valid writes
committed; code 1 means an execution error. All-skipped recovery reports
`storage_status: failed` and `written_count: 0`. Existing rows rejected by the
constraint retain their old values. Original job status/export metadata stay
unchanged. No source/model calls or invented defaults are used.

From production `nexgent/`, rebuild the writer, then recover:

```bash
sudo docker compose -f compose.prod.yaml up -d --build --no-deps weekly-report-worker
sudo docker compose -f compose.prod.yaml exec -T weekly-report-worker \
  uv run --no-sync python -m apps.workers.recover_weekly_report_storage \
  5622bbed-ac43-48b8-8121-e3f0c2f7c82d \
  --expected-count 6437 --write --skip-not-null
```

The updated writer module is required; streaming only the script into an old
image is insufficient. If every row is rejected on the same column, correct
the table/writer mismatch before retrying. This option does not repair schema
constraints or defaults.

Selective recovery validation: 33 focused tests passed; two PostgreSQL tests
were skipped without `WEEKLY_REPORT_TEST_DATABASE_DSN`. The full suite had
376 passes, three skips, and one pre-existing contract failure expecting the
old Monday 03:00 cron. Changed-file Ruff, LangGraph validation, production
Compose rendering, and the weekly-reporter skill validator passed. Whole-tree
Ruff still reports the two unrelated RAG/import sorting issues. Live production
writes and image deployment were not executed in this session.

## Explicit insert timestamps (2026-09-08)

Production recovery identified `created_at` NOT NULL failures for all 6,437
reports. The writer now supplies `NOW()` for both `created_at` and `updated_at`
on INSERT, without depending on table defaults. Conflicting ward/week updates
preserve `created_at` and refresh `updated_at`. This applies to regular bulk
finalization and recovery, and requires rebuilding the worker image. No table
alteration or report regeneration is required. Retry recovery with `--write`
after rebuilding; `--skip-not-null` remains optional for other rejected rows.
