# Weekly report completion notification

Date: 2026-09-29

The Monday 01:00 Asia/Seoul pipeline submits a Slack notification through the
product backend **after production migration commits**. For a September 28 run,
it compares September 21–27 with September 14–20. This operational summary
contains aggregate counts only, never subscriber names, addresses or reports.

## Local database coverage (2026-10-26)

All new completion-notification coverage reads now use the local agent database
configuration. No target database credentials or SSH tunnel are used. This
supersedes the earlier production-coverage permission guidance. Migration still
commits to production before completion notification; its connection is unchanged.
See [local coverage implementation and recovery](../../docs/08-implementation/weekly-report-local-notification-coverage.md).

## Device relationship correction (2026-10-26)

Selection and coverage now share an `EXISTS` check through the location/device
relationship. `has_device` is a derived value, not a physical ward column.
See [fix and rollout](../../docs/08-implementation/weekly-report-device-relationship-fix.md).

## Counting contract

- Population: every subscriber currently present in the local database
  `ansimk.resources_ward` with a device linked through `resources_location`,
  used identically for both weeks. Offline but linked devices remain eligible.
- Skipped reports: current local wards without a linked device, shown
  separately by region and overall. They count as skipped even when a stored
  report exists, and never enter eligible population, successes or missing rates.
  These are current-roster exclusion counts, not historical device-state counts
  or worker skip logs.
- Region: municipality tokens in `address`: 울진/울진군, 영덕/영덕군,
  광명/광명시; all remaining and missing addresses are 기타. Street names such
  as 광명로 do not select 광명. Each subscriber belongs to exactly one group.
- Success: a local `archive.resources_ward_weekly_report` row exists for the
  subscriber and reporting Monday. Existing reports count; these counts measure
  coverage, not this run's SQL insert count.
- Failure (missing): population minus success. Counts measure local storage, including reports skipped by production
  migration. They do not verify production coverage.
- Missing rate: failure / population × 100; empty groups display `—`.
  Both weekly rates and their percentage-point difference are shown. The
  headline additionally compares missing counts.

The schema has no ward enrollment timestamp. This explicitly compares the
current roster, not reconstructed historical membership. Deleted subscribers
and historical address changes cannot be recovered. Both weeks are read in one
repeatable-read, read-only local transaction.

## Native Korean Slack layout

The notification now uses the backend's validated native `blocks` API: header,
summary, date context, divider, a real Slack table, divider and full calculation
notes. Version 2 coverage snapshots add an eighth column,
`기기 미연결·제외(명)`, and an overall skipped count in the summary and fallback.
The table has ten data rows, pairing both weeks for
each region. It retains 가입자, 성공, 실패·누락, 누락률 and 전주 대비 누락률;
percentage-point changes and all original definitions have been restored.
Numbers are right-aligned and cells support wrapping. The complete content is
also available in the accessible fallback. No information is shortened away.

See the [full example](weekly-report-native-table-review.md) and
[backend API contract and rollout](../../docs/08-implementation/slack-notification-native-blocks.md).
Version 1 snapshots keep their original seven-column format. Frozen pending
or accepted notifications retain their original layout on retry.
Previous test messages in the private `#nexgent-test` channel exercised older
layouts through the direct backend sender. The new native layout was subsequently delivered successfully through the backend
sender to `#nexgent-test` (timestamp `1790670192.238509`), using the same verified
production snapshot. The deployed API-to-worker path still needs verification
following the earlier service-token HTTP 401 responses.

## Configuration and deployment

Updated 2026-10-06: `backend/prod.env` is the sole notification configuration
for the backend, notification worker, weekly-report scheduler, and monitor.
There is no separate weekly-reporter enable flag or copied service token:

```dotenv
NEXGENT_SLACK_ENABLED=true
NEXGENT_NOTIFICATION_SERVICE_TOKEN=YOUR_EXISTING_BACKEND_SERVICE_TOKEN
NEXGENT_SLACK_BOT_TOKEN=YOUR_EXISTING_SLACK_BOT_TOKEN
NEXGENT_SLACK_CHANNELS={"default":"YOUR_SLACK_CHANNEL_ID"}
```

When `NEXGENT_SLACK_ENABLED=true`, the reporter submits completion and failure
notifications automatically. False disables both. The backend remains the only
Slack sender; the scheduler uses the service token and the `default` destination
alias at the fixed internal `http://backend:8000` API. The bot token and channel
ID are consumed by the backend. Enabled reporter settings require a valid
service token and `default` channel mapping; invalid values fail configuration
without exposing secrets. Backend migrations and its notification worker must
also be available. See the [backend service contract](../../docs/08-implementation/slack-notification-service.md).

Production Compose mounts `backend/prod.env` read-only at
`/run/ax-notifications/prod.env` in the scheduler and independent monitor.
Settings are read from that file for each notification/monitor attempt, so cron
does not depend on inherited environment variables. Neither `agents/.env` nor
process overrides supply notification settings; all old
`WEEKLY_REPORT_NOTIFICATION_*` variables are retired and ignored. Production
must have this file: the bind mount refuses to create a missing host path.
Development/agent-only Compose does not mount production notification secrets
and notifications stay disabled there. The scheduler still mounts `agents/.env`
for its separate source-database/migration configuration.

Recreate the production scheduler/monitor to add the new mount. Backend and
notification-worker environment changes require their recreation as usual.
Existing receipts and immutable pending payloads are retained. A pending payload
created with a different backend URL still requires operator reconciliation;
this change does not silently redirect or resend accepted messages.

The scheduler image now installs frozen workspace dependencies to use the
shared HTTP integration and workflow-owned aggregation/formatting code. Cron
invokes `/app/.venv/bin/python`. Rebuild from `agents/`:

```bash
docker compose -f ../compose.prod.yaml up -d --build --no-deps weekly-report-scheduler
```

No application schema migration is added. Coverage uses
`WEEKLY_REPORT_STORAGE_DATABASE_DSN`, falling back to `ANSIMK_DATABASE_DSN`,
from the process environment or `agents/.env`. `SOURCE_DATABASE_DSN` and target
credentials are not used for coverage. The local role needs SELECT on ward
`id`/`address`, location `id`/`ward_id`, device `location_id`, and local archive
report ward/week columns. Slack delivery configuration remains in `backend/prod.env`.

## Recovery and delivery semantics

1. Generation and migration retain their strict success gates. Failed/partial
   generation or failed migration never emits a completion notification.
2. The scheduler writes its per-week migration receipt first.
3. A separate invocation of the database helper runs
   `--week-start YYYY-MM-DD --coverage-output PATH`, without `--write`.
   This mode bypasses SSH and only reads local coverage and saves aggregate JSON.
4. The frozen message, backend URL and stable idempotency key
   `weekly-report:production:YYYY-MM-DD:coverage-v1` are persisted before POST.
   Retain the scheduler volume containing snapshots and immutable requests.
5. The shared adapter sends `POST /api/notifications/slack` with Bearer auth.
   At most three attempts have 15-second request timeouts and bounded backoff.
   Redirects and permanent errors are rejected; response bodies and tokens never
   enter logs. All attempts reuse the same key and payload.
6. A valid `202` persists the backend job ID/status in a separate notification
   receipt. Acceptance means **queued**, not delivered. Backend workers own
   Slack retries; inspect `GET /api/notifications/{id}` with the same token for
   final status. A replay returning `failed` is surfaced as an error.

After snapshot/API failure, the pipeline exits nonzero and logs
`weekly_report_notification_failed`. The migration receipt remains valid.
Resume with the original reporting Monday:

```bash
docker compose -f ../compose.prod.yaml exec weekly-report-scheduler \
  /app/.venv/bin/python -m apps.weekly_report_scheduler.pipeline --week-start 2026-09-21
```

A valid migration receipt skips generation/migration and resumes only the
notification. An accepted notification receipt suppresses further POSTs.
Interruption after backend acceptance but before receipt persistence reuses the
immutable key/body. The backend rejects changed payloads with the same key.
Changing the backend URL during pending recovery is rejected. Do not delete
receipts to force resend; terminal backend failure requires an intentional new
notification key through its API. No automatic catch-up or restart retry is
added to cron. Backend delivery can remain queued while its worker is offline.
Slack delivery remains at least once: a backend send/ack crash can duplicate a
message. Existing human-approved per-report delivery is unchanged.

## Verification checkpoint

Acceptance gates: committed-target trigger; both weeks/five groups, missing
rates and missing-count changes; current-roster disclosure; aggregate-only payloads; bounded
backend submission; immutable retries; independent recovery.

Tests cover formatting, empty denominators, invalid snapshots, commit ordering,
failed migration, retries, redacted configuration and read-only commands.
The PostgreSQL integration test substitutes synthetic CTE fixtures for both
tables to verify real region SQL, duplicates/orphans and week filtering without
reading or writing application data. Container rollout and live Slack delivery
are separate deployment checks.

Verification on 2026-09-29: full offline regression passed outside the sandbox
(sandboxed async attachment tests stalled); the additional focused notification
suite and backend schema contract passed. The PostgreSQL synthetic read-only
fixture passed. LangGraph validation (four graphs), agent and production Compose
rendering, skill validation, and changed-file Ruff checks passed. Full-repository
Ruff reports two pre-existing ordering violations in integration exports and a
RAG graph test. Docker image build was not run because daemon access requires
interactive sudo authentication. No service was deployed and no Slack message
was sent.
