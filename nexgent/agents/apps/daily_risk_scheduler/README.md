# Daily risk-count agent

Configuration update (2026-10-27): all agent configuration now comes from
`agents/.env`; see [unified environment](../../docs/unified-environment.md).
Production migration uses `LIVE_PROD_*` and development migration uses
`LIVE_DEV_*`. Older per-tool env files are no longer read.

Runs every day at **05:15 Asia/Seoul**, using cron `15 5 * * *`. Each run
processes the **full previous local calendar day**: midnight inclusive through
the next midnight exclusive, including every instant in 23:59. For example,
October 26 at 05:15 processes October 25 only. The November 1 run updates
October's monthly row.

The deterministic workflow reads `archive.resources_ward` and
`archive.analysis_wardevaluation`, then updates
`archive.resources_ward_monthly_risk_count` in the same local database.
It makes no model calls. It does not copy rows to live dev or production.
The existing manual history migration remains available for backfills.

For every source ward, the selected date is replaced in `risk_days` and
`danger_stable_days`; other dates and months are preserved. DANGER counts
once per date. Recovery requires a strictly later STABLE on the same date;
intermediate states are allowed. Both totals equal their array lengths.
New ward/month rows start with the selected day's facts only. This workflow
does not initialize earlier history; use the manual migration first when
historical month-to-date totals are required. An empty evaluation window
removes that date's existing membership and creates zero rows for new wards.
Run only after the previous day's archive evaluations are ready.

The workflow uses a repeatable-read transaction and the manual migration's
target table lock, with a ten-second lock timeout and a thirty-minute SQL
statement timeout. The commit is its durable checkpoint. Reruns reconcile
membership instead of incrementing totals and preserve IDs/creation timestamps.
Unchanged rows retain their update timestamps. Failure rolls back the date;
an uncertain commit can be reconciled by rerunning the same date.
JSON start/completion/failure events go to container logs. Completion is emitted
only after commit. Failures exit nonzero without exposing database messages.

## Run and recovery

From `agents/`, preview first or apply an explicit completed date:

```bash
.venv/bin/python -m apps.daily_risk_scheduler.run
.venv/bin/python -m apps.daily_risk_scheduler.run --date 2026-10-25
.venv/bin/python -m apps.daily_risk_scheduler.run --date 2026-10-25 --apply
```

Default date is yesterday in Seoul, independent of the caller's system timezone.
Current/future dates are rejected. The CLI previews by default; cron uses `--apply`.
Database settings use only exported values and `agents/.env`, selecting
`SOURCE_DATABASE_DSN`, then `WEEKLY_REPORT_STORAGE_DATABASE_DSN`, then
`ANSIMK_DATABASE_DSN`. No nested playground env file is read.

The scheduler belongs to the existing root environment stacks; it has no
separate Compose file. From `nexgent/`, start development (opt-in `scheduled`
profile) or production:

```bash
# Development
docker compose -f compose.yaml --profile scheduled up -d --build daily-risk-scheduler
docker compose -f compose.yaml logs -f daily-risk-scheduler

# Production
docker compose -f compose.prod.yaml up -d --build daily-risk-scheduler
docker compose -f compose.prod.yaml logs -f daily-risk-scheduler
```

Both services use `agents/.env` and host networking to reach the local database.
Set `SOURCE_DATABASE_DSN` in that env file if a dedicated migration connection
is needed. Production includes this service in normal stack startup; development
uses the same opt-in profile as the weekly scheduler. To stop only this service,
use `docker compose -f compose.yaml stop daily-risk-scheduler` (or
`-f compose.prod.yaml` for production).

The container must be running at 05:15. Cron does not catch up missed dates,
and a failed run is not automatically retried. Inspect `daily_risk_failed` or
missing `daily_risk_completed` events and explicitly replay missed dates
oldest first. Replaying an older date preserves all other saved dates.
Rebuild/recreate the container to activate code or cron changes.

## Slack status notifications

Every `--apply` invocation, including cron and manual replay, submits an
English operational status to the backend's durable Slack queue after reconciliation.
Both success and failure messages use these five fields, with actual run timestamps
in Korea time:

```text
Status: Success
Title: Daily Risk Count
Start time: 2026-10-27 05:15:00 KST
End time: 2026-10-27 05:16:00 KST
Message: Successfully done!
```

Failures use `Status: Fail` and an English issue identifying configuration,
connection, or reconciliation/commit confirmation failure, with a reference to
`daily_risk_failed` logs. Raw exception messages and credentials are excluded.
The message omits ward counts, write counts and archive storage details.
An uncertain commit is not reported as a confirmed rollback. Previews do not
send notifications. A manual rerun produces a new status message.

The pending parent Compose patch mounts `agents/.env` read-only at
`/app/.env`, sharing the weekly reporter's
`NEXGENT_SLACK_ENABLED`, `NEXGENT_NOTIFICATION_SERVICE_TOKEN`, and
`NEXGENT_SLACK_CHANNELS` configuration. The backend owns the Slack bot and
`daily_risk` destination, mapped to `C0C24T2124E` in `NEXGENT_SLACK_CHANNELS`.
The existing `default` alias remains available for other notifications.
Agent notification client credentials now live in `agents/.env`. An explicit
false enable flag disables notifications; a missing unified file also leaves
them disabled. Apply the parent Compose patch before recreating this service.

Because the scheduler uses host networking, production submits through
`http://127.0.0.1:${PROD_BACKEND_PORT:-8001}`, configured by Compose as
`DAILY_RISK_NOTIFICATION_BASE_URL`. Backend authentication and its notification
worker must be available. Rebuild/recreate from `nexgent/` after updating code:

```bash
sudo docker compose -f compose.prod.yaml up -d --build daily-risk-scheduler
sudo docker compose -f compose.prod.yaml up -d --force-recreate backend notification-worker
```

Recreate the backend and notification worker when changing channel mappings
because Compose loads their environment at container creation. The Slack bot
must be a member of `C0C24T2124E`. Missing `daily_risk` configuration fails
notification submission rather than falling back to another channel.

`daily_risk_notification_accepted` records backend queue acceptance, not confirmed
Slack delivery. The backend worker owns delivery and its retries. Submission
uses three bounded attempts with one immutable idempotency key and payload.
Configuration/submission errors emit `daily_risk_notification_failed` without
changing the database run's exit status; database failures still exit nonzero.
Before backend acceptance there is no local notification outbox or automatic
resend. Inspect failures and replay the date if another status is needed; replay
reconciles the database again and reports that invocation's counts. Disabled
notifications emit `daily_risk_notification_disabled`. No missed-run monitoring
or automatic catch-up is added.

## Verification

```bash
.venv/bin/python -m pytest tests/unit/test_daily_risk_counts.py tests/unit/test_daily_risk_notification.py
DAILY_RISK_TEST_DATABASE_DSN=postgresql://... .venv/bin/python -m pytest tests/integration/test_daily_risk_counts_postgres.py
```

The PostgreSQL test creates only synthetic temporary tables. It verifies
midnight/end-of-day bounds, recovery ordering, repeated danger, no evaluations,
other-date/month preservation, preview safety, late corrections and idempotence.
