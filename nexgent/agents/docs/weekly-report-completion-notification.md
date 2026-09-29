# Weekly report completion notification

Date: 2026-09-29

The Monday 01:00 Asia/Seoul pipeline submits a Slack notification through the
product backend **after production migration commits**. For a September 28 run,
it compares September 21–27 with September 14–20. This operational summary
contains aggregate counts only, never subscriber names, addresses or reports.

## Counting contract

- Population: every subscriber currently present in production
  `ansimk.resources_ward`, used identically for both weeks.
- Region: municipality tokens in `address`: 울진/울진군, 영덕/영덕군,
  광명/광명시; all remaining and missing addresses are 기타. Street names such
  as 광명로 do not select 광명. Each subscriber belongs to exactly one group.
- Success: a production `resources_ward_weekly_report` row exists for the
  subscriber and reporting Monday. Existing reports count; these counts measure
  coverage, not this run's SQL insert count.
- Failure (missing): population minus success. Locally generated reports that
  were not stored in production cannot count as success. Wards absent from the
  production roster, including migration skips, are excluded.
- Missing rate: failure / population × 100; empty groups display `—`.
  Both weekly rates and their percentage-point difference are shown. The
  headline additionally compares missing counts.

The schema has no ward enrollment timestamp. This explicitly compares the
current roster, not reconstructed historical membership. Deleted subscribers
and historical address changes cannot be recovered. Both weeks are read in one
repeatable-read, read-only production transaction.

## Native Korean Slack layout

The notification now uses the backend's validated native `blocks` API: header,
summary, date context, divider, a real Slack table, divider and full calculation
notes. The table has seven columns and ten data rows, pairing both weeks for
each region. It retains 가입자, 성공, 실패·누락, 누락률 and 전주 대비 누락률;
percentage-point changes and all original definitions have been restored.
Numbers are right-aligned and cells support wrapping. The complete content is
also available in the accessible fallback. No information is shortened away.

See the [full example](weekly-report-native-table-review.md) and
[backend API contract and rollout](../../docs/08-implementation/slack-notification-native-blocks.md).
Frozen pending or accepted notifications retain their original layout on retry.
Previous test messages in the private `#nexgent-test` channel exercised older
layouts through the direct backend sender. The new native layout was subsequently delivered successfully through the backend
sender to `#nexgent-test` (timestamp `1790670192.238509`), using the same verified
production snapshot. The deployed API-to-worker path still needs verification
following the earlier service-token HTTP 401 responses.

## Configuration and deployment

Add to `agents/.env`, already mounted read-only by the scheduler:

```dotenv
WEEKLY_REPORT_NOTIFICATION_ENABLED=true
WEEKLY_REPORT_NOTIFICATION_API_URL=http://backend:8000
WEEKLY_REPORT_NOTIFICATION_SERVICE_TOKEN=REPLACE_WITH_BACKEND_SERVICE_TOKEN
WEEKLY_REPORT_NOTIFICATION_DESTINATION=default
```

The feature defaults to disabled until configured. The service token must match
backend `NEXGENT_NOTIFICATION_SERVICE_TOKEN`; this is not a Slack bot token.
Destination must be an alias in backend `NEXGENT_SLACK_CHANNELS`. Enable backend
notifications, apply its migrations and run its notification worker. See the
[backend service contract](../../docs/08-implementation/slack-notification-service.md).

Settings are read from the mounted `.env`, with process environment overrides.
No parent Compose edit or additional secret mount is needed. The agent-only
Compose stack needs a reachable backend URL because it does not launch the
product backend. Production remains the automatic schedule owner; leave
development's `scheduled` profile disabled.

The scheduler image now installs frozen workspace dependencies to use the
shared HTTP integration and workflow-owned aggregation/formatting code. Cron
invokes `/app/.venv/bin/python`. Rebuild from `agents/`:

```bash
docker compose -f ../compose.prod.yaml up -d --build --no-deps weekly-report-scheduler
```

No application schema migration is added. The existing production migration
role needs SELECT on ward `id`/`address` and report ward/week columns.

## Recovery and delivery semantics

1. Generation and migration retain their strict success gates. Failed/partial
   generation or failed migration never emits a completion notification.
2. The scheduler writes its per-week migration receipt first.
3. A separate invocation of the existing SSH script runs
   `--week-start YYYY-MM-DD --coverage-output PATH`, without `--write`.
   This mode only reads production coverage and saves aggregate JSON.
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
