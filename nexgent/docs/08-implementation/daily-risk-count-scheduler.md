# Daily risk-count scheduler

Date: 2026-10-26

The deterministic `agents/workflows/daily_risk_counts` workflow updates
`archive.resources_ward_monthly_risk_count` from archive ward evaluations for
the full previous Seoul calendar day. It runs at 05:15 Asia/Seoul, replacing
only the selected date in danger/recovery arrays and deriving matching counts.
Other dates are preserved; a transactional table lock serializes writers and
reruns are idempotent. No live-data copy or model call is involved.

The scheduler service is declared directly in the existing root `compose.yaml`
and `compose.prod.yaml`. Development uses the opt-in `scheduled` profile;
production starts it normally. Both use `agents/.env` and host networking.
There is no daily-risk-specific Compose file. The independent scheduler
container retains its own Dockerfile and cron entry.

From `nexgent/`:

```bash
# Development
docker compose -f compose.yaml --profile scheduled up -d --build daily-risk-scheduler
# Production
docker compose -f compose.prod.yaml up -d --build daily-risk-scheduler
```

The implementation passed twelve unit tests, one synthetic temporary-table
PostgreSQL test, lint checks, and a read-only archive preview for 6,695 wards.
The Compose integration is validated with both environment configurations and
assertions on the resolved service, profile, image and build context. No image
build, deployment or scheduled business-table write was performed. The commands
above remain the activation steps. Cron does not catch up missed dates; use
explicit `--date` runs for recovery.

See [workflow operations](../../agents/apps/daily_risk_scheduler/README.md)
for previews, manual replay, database settings and limitations.
