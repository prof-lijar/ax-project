# Weekly report local notification coverage

Date: 2026-10-26 (Asia/Seoul)

## Implementation and data meaning

All newly collected Slack completion coverage now reads the local database.
The exporter uses `WEEKLY_REPORT_STORAGE_DATABASE_DSN`, falling back to
`ANSIMK_DATABASE_DSN`, from the process environment or `agents/.env`. For each
key, the process value takes precedence over the file value. The currently
configured local role is `nextor` on `ansimk_archive`.

One local connection and one repeatable-read, read-only transaction cover both
weeks. Population, regions and linked-device eligibility come from local
`ansimk.resources_ward`, `ansimk.resources_location`, and
`ansimk.resources_device`; saved-report existence comes from local
`archive.resources_ward_weekly_report`. All those tables must be readable through
the selected local connection. An override pointing to a storage-only database
without the roster tables is unsupported.

The coverage exporter ignores `SOURCE_DATABASE_DSN`, `TARGET_DB_*`, and
`SSH_*`. `migrate.sh` dispatches `--coverage-output` directly to Python before
checking SSH dependencies or production credentials. Coverage mode also bypasses
loading `playground/weekly-reporter/.env`. The production migration path retains
its existing source override, target credentials and SSH forwarding.

Completion notification still follows successful production migration. Its
coverage numbers now describe local storage, including locally saved reports
that production migration skipped. The Slack footer explicitly says local DB;
these counts do not independently verify production coverage. Slack API tokens,
destination and enable flag remain in `backend/prod.env`.

Migration receipts and notification idempotency are unchanged. Previously frozen
snapshots/payloads retain their prior data and wording, and accepted notifications
are not resent. The internal `weekly-report:production:...` notification key is
retained for retry compatibility; it no longer describes the coverage data source.
The permission grants discussed earlier for production coverage are unnecessary
for this new local coverage path.

## Validation

113 focused migration, coverage, pipeline, and notification deployment tests
passed. Tests verify local storage/source DSN selection, exclusion of migration
overrides and target credentials, bypass of production dotenv loading and SSH,
local report-table SQL, atomic snapshot output, connection cleanup on failure,
and retained receipt/notification behavior. Changed-file Ruff passed.

A live read-only invocation of the shell coverage helper for October 19 succeeded
against the configured local DB, writing only an aggregate snapshot under `/tmp`.
No SSH tunnel was opened, production data changed, or Slack message submitted.
The read-only PostgreSQL CTE coverage fixture also passed. `bash -n` and
`git diff --check` passed.

From `agents/`, run the focused offline checks:

```bash
.venv/bin/pytest --disable-warnings tests/unit/test_weekly_report_migration.py tests/unit/test_weekly_report_completion_notification.py tests/unit/test_weekly_report_schedule_pipeline.py tests/contract/test_weekly_report_notification_deployment.py
```

## Deployment and notification recovery

Production containers were not rebuilt: Docker access requires interactive sudo.
Live backend queue acceptance and Slack delivery remain unverified. Between
active runs, rebuild the scheduler from `nexgent/`, preserving any production
overlay arguments:

```bash
sudo docker compose -f compose.prod.yaml up -d --build --no-deps weekly-report-scheduler
```

Optionally verify the local DB coverage path inside the rebuilt container
without sending a notification:

```bash
sudo docker compose -f compose.prod.yaml exec -T weekly-report-scheduler bash /app/playground/weekly-reporter/migrate.sh --week-start 2026-10-19 --coverage-output /tmp/local-weekly-coverage.json
```

Resume the existing failed October 19 notification with the same regeneration
key and the retained scheduler state volume:

```bash
sudo docker compose -f compose.prod.yaml exec -T weekly-report-scheduler /app/.venv/bin/python -m apps.weekly_report_scheduler.pipeline --week-start 2026-10-19 --regenerate device-join-v1
```

The existing regeneration receipt skips generation and production migration.
The prior permission failure occurred before a coverage snapshot was saved, so
this retry collects a new local snapshot, then submits the completion message.
Verify backend acceptance and final Slack delivery separately. Do not change
the regeneration key for notification-only recovery.

## Notification-only delivery verified (2026-10-26)

At the operator's explicit request, completion notification for October 19 was
submitted independently using local coverage and the production backend's
notification service configuration. No generation or migration ran. The snapshot
contained 6,295 eligible wards, 6,295 saved reports, and 363 device-unlinked skips.
The backend notification `159e38a0-440b-4770-8276-e4448d8b7a7a` transitioned from
`queued` to `sent` in one attempt, with Slack timestamp `1792956595.394409` and
delivery time `2026-10-25T19:29:55.528547Z` (October 26, 04:29:55 KST).

This direct recovery used the normal per-week notification idempotency key and
saved its immutable snapshot/request/acceptance receipt under
`/tmp/nexgent-weekly-notification-recovery-20261019`. That temporary recovery state
is separate from the scheduler container volume; the backend retains the
idempotent acceptance record. Do not use a new notification key to resend this
completion. This verifies the local coverage and backend-to-Slack delivery path;
deployment of the updated scheduler image remains an operator step.
