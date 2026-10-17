# Weekly Report Scheduler

This private cron service starts durable Weekly Reporter generation every
Monday at 01:00 in `Asia/Seoul`. The cron expression is `0 1 * * 1`.

Each run targets the previous fully completed Monday-through-Sunday period and
includes every ward in `ansimk.resources_ward`, even without weekly records. Each job
requests up to 10,000 reports by default; the pipeline follows continuation
cursors until discovery is exhausted. Idempotency keys include the reporting
Monday, the all-ward policy, and a cursor hash for subsequent jobs.

After submission, the service polls the private bulk control API every 30
seconds. All batches share a 24-hour generation/polling deadline. Only
`completed` with matching completed/discovered counts and no failed or unfinished
items confirms complete batch storage. After the last continuation batch, it runs
`playground/weekly-reporter/migrate.sh --write --week-start YYYY-MM-DD`, using
the submitted reporting Monday, with a one-hour migration deadline. Partial,
failed, cancelled, cancelling, and expired jobs
do not migrate. The service does not generate reports or call the model.

For example, Monday 2026-09-14 submits the week starting 2026-09-07, then
migrates with `--week-start 2026-09-07` after local storage succeeds.

The pipeline serializes invocations with a local file lock, and saves a
per-week `all-wards-v1` success receipt with batch IDs and report count only
after migration exits successfully. Legacy receipts do not suppress full-ward
generation. A rerun
with a receipt skips submission and migration and resumes any configured pending
completion notification. Without a receipt, the same
idempotency key resumes the existing bulk job. If interrupted after target
commit but before receipt creation, retrying may repeat the upsert and refresh
`updated_at`; delivery is not exactly-once. There is no automatic restart
catch-up or migration retry. Failures log a content-free pipeline event and
exit nonzero; local reports remain saved.

Each attempt also saves its current stage, safe job counts and a heartbeat under
`runs/`. Normal errors trigger a best-effort Korean failure notification. Deploy
the independent monitor below for abrupt process death and missed cron runs;
a stopped scheduler cannot send its own alert.

## Production rollout and recovery

Configure `playground/weekly-reporter/.env` using its README and ensure the
source DSN resolves to the bulk worker's local report database. Migration
reads local `archive.resources_ward_weekly_report` and writes production
`ansimk.resources_ward_weekly_report`; production schema is unchanged. The scheduler
image contains the migration scripts and SSH/Python dependencies; credentials
are mounted read-only at runtime. Do not combine this whole-week migration
with the optional outbox delivery overlay for the same reports.

The shared migration skips reports whose ward is absent from the production
ward table, prints each ward ID/week, and includes `skipped` in its summary.
Other reports commit normally, including when all selected reports are skipped.
The success receipt's report count is the locally generated count, not the
production inserted count. Rebuild `weekly-report-scheduler` to pick up the
updated migration script; no scheduler-specific skip flag is needed.

From the `agents` folder, deploy the scheduler with its required secret mounts,
durable receipts, and SSH known-host volume:

```bash
docker compose -f ../compose.prod.yaml up -d --build --no-deps weekly-report-scheduler
```

For failure monitoring, include the overlay and start both processes:

```bash
docker compose -f ../compose.prod.yaml -f compose.weekly-report-monitor.prod.yaml up -d --build --no-deps weekly-report-scheduler weekly-report-monitor
```

The monitor shares the scheduler state volume and existing notification
configuration. It runs independently of scheduler/bulk API readiness. See
[failure alerts](../../docs/weekly-report-failure-notification.md) for detection
times, durable retry and outage limitations.

The production Compose file includes the migration mounts directly. The agent-only
`compose.yaml` includes them under its existing opt-in `scheduled` profile.

To resume an interrupted or failed migration for a specific reporting week:

```bash
docker compose -f ../compose.prod.yaml exec weekly-report-scheduler /app/.venv/bin/python -m apps.weekly_report_scheduler.pipeline --week-start 2026-09-07
```

The command without `--regenerate` does not regenerate a retained existing job.
Retain `/var/lib/ax/weekly-report-scheduler` across container replacement;
`WEEKLY_REPORT_SCHEDULE_STATE_ROOT` can override that directory for local execution.

## Regenerate a week and write to the live database

Run these commands from the `agents/` directory. The example targets
**October 5–11, 2026**, in `Asia/Seoul`; `--week-start` is the inclusive Monday.

Deploy the corrected source API and the scheduler's regeneration option once,
between jobs. Skip this step if these changes are already deployed; do not
rebuild/recreate the containers while a generation or migration is running.

```bash
sudo docker compose -f ../compose.prod.yaml up -d --build --no-deps weekly-report-api weekly-report-scheduler
```

Start regeneration and keep this terminal open through the migration:

```bash
sudo docker compose -f ../compose.prod.yaml exec weekly-report-scheduler \
  /app/.venv/bin/python -m apps.weekly_report_scheduler.pipeline \
  --week-start 2026-10-05 --regenerate ansimk-v1
```

Deploy the corrected source API before starting regeneration. The run submits
fresh jobs for every source ward, waits for all batches to commit local reports,
and invokes the existing whole-week production upsert. A generation failure
prevents migration. Production rows for absent wards are still skipped.

`RUN_KEY` is 1–32 letters, digits, hyphens or underscores, starting with a letter
or digit. It identifies a regeneration, not a change to the reporting week.
Repeat the same key to reuse jobs and retry an interrupted migration; successful
regenerations skip generation and migration on repeat. Use a new key only for
another fresh generation (or after fixing a terminal generation failure).

Regeneration receipts are stored under
`regenerations/<RUN_KEY>/<Monday>.json`. Original cron receipts are preserved;
the same global pipeline lock, durable attempt tracking, continuation checks,
and migration success gate apply. Existing per-week completion notification
receipts are reused, so this does not create a separate correction announcement.

The scheduler submits the work to `weekly-report-worker`, which runs the agent.
The scheduler then waits and migrates the saved reports automatically. You do
not need to run `playground/weekly-reporter/migrate.sh` separately for this path.
That standalone script only copies existing reports and cannot regenerate them.

## Watch live progress

Open a second terminal in `agents/`. Copy the `job_id` from the original
terminal's `weekly_report_schedule_submitted` event. The ID below is the
October 17 regeneration example; replace it with the submitted ID for another run.

Watch progress every five seconds:

```bash
sudo watch -n 5 'docker compose -f ../compose.prod.yaml exec -T weekly-report-worker /app/.venv/bin/python -m apps.workers.weekly_report status e379208b-f40a-4f55-af50-4a573545730c'
```

Or check once:

```bash
sudo docker compose -f ../compose.prod.yaml exec -T weekly-report-worker \
  /app/.venv/bin/python -m apps.workers.weekly_report status \
  e379208b-f40a-4f55-af50-4a573545730c
```

| Field | Meaning |
| --- | --- |
| `status` | Current generation state; `completed` includes local report storage, not production migration. |
| `discovered_count` | Wards found so far in this batch; may increase until `producer_done` is true. |
| `completed_count` | Reports completed in this batch. |
| `pending_count` / `running_count` | Reports waiting / currently being processed. |
| `failed_count` | Failed reports; any failure prevents the scheduler from migrating the batch. |
| `selection_truncated` / `next_cursor` | More wards require another batch; the scheduler submits it automatically and prints another job ID. |

To follow worker logs:

```bash
sudo docker compose -f ../compose.prod.yaml logs -f --since 10m weekly-report-worker
```

Worker logs include other jobs; use the status command for this job's counts.
`Ctrl+C` in the watch or log terminal stops monitoring only. Keep the original
pipeline terminal running; do not rerun generation merely to check progress.

## Confirm the live database write

In the original pipeline terminal, look for these events in order:

1. `weekly_report_migration_started`: all generation batches passed the local
   storage checks and production migration is starting.
2. `"mode": "committed"`: the migration transaction committed. Review its
   `insert`, `update`, and `skipped` counts; wards absent from production are skipped.
3. `weekly_report_migration_completed`: the scheduler recorded migration success.

The manually executed pipeline writes its output to the original `docker compose
exec` terminal; `docker compose logs weekly-report-scheduler` is not a substitute
for that output. A job showing `completed` alone does not confirm a live DB write.

You can also inspect this regeneration's durable migration-success receipt:

```bash
sudo docker compose -f ../compose.prod.yaml exec -T weekly-report-scheduler \
  cat /var/lib/ax/weekly-report-scheduler/regenerations/ansimk-v1/2026-10-05.json
```

The receipt is written only after successful migration. Its `report_count` is
the locally generated total, not the number inserted in production; use the
migration summary for production skips. Adjust the run key/date and the state
root if configured differently. Completion notification happens afterward and
has its own acceptance state.

For an interrupted migration, rerun the exact regeneration command with the
same week and run key. Inspect target state before retrying an uncertain commit:
an interrupted run may have committed before saving its receipt, and retrying
can repeat the upsert. A terminal failed generation requires fixing the cause
and using a new run key. See [full-coverage recovery](../../docs/weekly-report-completeness.md)
for the completeness policy.

## Configuration

Optional completion notifications use the backend's durable Slack API after
production migration. `NEXGENT_SLACK_ENABLED=true` in `backend/prod.env`
automatically enables completion and failure notifications. The scheduler and
monitor read that file through a production-only read-only mount, reuse
`NEXGENT_NOTIFICATION_SERVICE_TOKEN`, and submit to `http://backend:8000`
with destination `default` from `NEXGENT_SLACK_CHANNELS`. Separate scheduler
notification variables are retired; `agents/.env` is used only for other
configuration. Both weeks' production report coverage is grouped by subscriber address
with missing rates and percentage-point comparisons. Notification failure keeps
the migration receipt and can be resumed independently. See [notification
configuration and recovery](../../docs/weekly-report-completion-notification.md).

Bulk submission settings:

- `WEEKLY_REPORT_BULK_API_URL`, default
  `http://weekly-report-bulk-api:8090`;
- `WEEKLY_REPORT_SCHEDULE_MAX_REPORTS`, default `10000`;
- `WEEKLY_REPORT_SCHEDULE_TIMEOUT_SECONDS`, default `30`;
- `WEEKLY_REPORT_SCHEDULE_ATTEMPTS`, default `3`; and
- `WEEKLY_REPORT_SCHEDULE_RETRY_DELAY_SECONDS`, default `2`.

The schedule and reporting timezone are intentionally fixed to
`Asia/Seoul`. Changing the schedule requires a reviewed crontab and image
deployment; the current frontend controls do not reconfigure this service.

The production Compose stack (`../compose.prod.yaml`) starts this service by
default and is the
single automatic schedule owner. Development and agent-only Compose stacks
place it behind the `scheduled` profile to avoid duplicate weekly generation
when multiple environments share the same source, writer, or model systems.

Keep the `scheduled` profile disabled in development when production scheduling
is enabled. Production should be the only automatic schedule owner.
