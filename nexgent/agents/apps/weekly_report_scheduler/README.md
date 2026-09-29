# Weekly Report Scheduler

This private cron service starts durable Weekly Reporter generation every
Monday at 01:00 in `Asia/Seoul`. The cron expression is `0 1 * * 1`.

Each run targets the previous fully completed Monday-through-Sunday period and
includes every ward in `resources_ward`, even without weekly records. Each job
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

## Production rollout and recovery

Configure `playground/weekly-reporter/.env` using its README and ensure the
source DSN resolves to the bulk worker's local report database. The scheduler
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

The production Compose file includes the migration mounts directly. The agent-only
`compose.yaml` includes them under its existing opt-in `scheduled` profile.

To resume an interrupted or failed migration for a specific reporting week:

```bash
docker compose -f ../compose.prod.yaml exec weekly-report-scheduler /app/.venv/bin/python -m apps.weekly_report_scheduler.pipeline --week-start 2026-09-07
```

This does not regenerate a retained existing job. Inspect target state before
retrying an uncertain commit. Retain `/var/lib/ax/weekly-report-scheduler`
across container replacement; `WEEKLY_REPORT_SCHEDULE_STATE_ROOT` can override
that directory for local execution. A failed generation job requires the
existing generation/storage recovery procedure before manual migration.
For the all-ward policy rollout and regeneration of a legacy week, see
[full-coverage recovery](../../docs/weekly-report-completeness.md).

Configuration:

Optional completion notifications use the backend's durable Slack API after
production migration. Set `WEEKLY_REPORT_NOTIFICATION_ENABLED=true`,
`WEEKLY_REPORT_NOTIFICATION_API_URL`, `WEEKLY_REPORT_NOTIFICATION_SERVICE_TOKEN`
and `WEEKLY_REPORT_NOTIFICATION_DESTINATION` in the existing mounted agent
`.env`. Both weeks' production report coverage is grouped by subscriber address
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
