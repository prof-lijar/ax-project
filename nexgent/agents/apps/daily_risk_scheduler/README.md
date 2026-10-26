# Daily risk-count agent

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
Database settings follow the existing migration: exported values and
`playground/.env`, then `SOURCE_DATABASE_DSN`, or
`WEEKLY_REPORT_STORAGE_DATABASE_DSN`, or `ANSIMK_DATABASE_DSN` (the latter two
also fall back to `agents/.env`). No new credentials or DDL are needed.

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

## Verification

```bash
.venv/bin/python -m pytest tests/unit/test_daily_risk_counts.py
DAILY_RISK_TEST_DATABASE_DSN=postgresql://... .venv/bin/python -m pytest tests/integration/test_daily_risk_counts_postgres.py
```

The PostgreSQL test creates only synthetic temporary tables. It verifies
midnight/end-of-day bounds, recovery ordering, repeated danger, no evaluations,
other-date/month preservation, preview safety, late corrections and idempotence.
