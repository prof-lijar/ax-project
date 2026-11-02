# Daily risk-count scheduler live database sync

## Production copy added (2026-11-02)

The existing `compose.prod.yaml` now selects `DAILY_RISK_SYNC_TARGET=both`.
Each applied run commits the local reconciliation, copies the processed month
to live dev, then copies it to `LIVE_PROD_DB_*` through `LIVE_PROD_SSH_*`.
Both destinations use `ansimk`; production credentials never fall back to dev.
Success follows all three commits. Previews perform neither live copy.

A failure stops the sequence and identifies the destination. Earlier commits
remain intact, with per-target completion events available in the logs.
Replaying the same date safely reconciles and recopies the month. The final
receipt includes `live_targets.dev` and `live_targets.prod`; `live` remains the
dev receipt for compatibility. Missing wards are skipped separately per target.

Rebuild/recreate the existing scheduler using the commands below to activate
this change. The November 2 implementation has not been deployed or verified
against live databases in this session.

Verification: 55 focused scheduler/notification/migration tests passed; five
opt-in PostgreSQL copy tests were skipped. Ruff, formatting, diff checks and
production Compose rendering passed. Both live destinations' settings validated
without opening database connections or displaying credentials.

## Live-dev rollout checkpoint (2026-10-30)

The following records the earlier dev-only behavior, superseded above.

The scheduler previously reported success after updating only the local archive.
Production Compose now explicitly sets `DAILY_RISK_SYNC_TARGET=dev`. After the
local commit, the scheduler copies the processed month's stored rows to
`LIVE_DEV_DB_*`, schema `ansimk`, through `LIVE_DEV_SSH_*`. The image includes
SSH and sshpass. Development defaults to local-only.

The workflow-owned copy implementation is shared with the manual migration.
It validates staged counts/arrays, skips wards absent from dev, upserts eligible
keys, and verifies them before committing. Manual migration retains its full
history scope; scheduled copies affect only the processed month. Completion
and success notifications follow both commits. Live failure leaves the local
commit intact, reports the failed stage, and can be recovered by replaying the
same date. No cross-database atomicity or automatic catch-up is added.

Each run processes yesterday in Seoul. November 1 finalizes October; November 2
creates November rows for November 1, including zero-count rows, for each source
ward. Live rows require matching dev wards. Older months remain separate.

Validation: 72 focused tests passed, with 13 opt-in SQL tests skipped in that
run; a separate PostgreSQL run passed all 11 selected checks using temporary
tables. Ruff, diff checks, live-dev settings validation and production Compose
rendering passed. The operator subsequently confirmed the deployed fix worked.

From `nexgent/`, activate changes and replay a completed date as needed:

```bash
sudo docker compose -f compose.prod.yaml up -d --build daily-risk-scheduler
sudo docker compose -f compose.prod.yaml exec daily-risk-scheduler /app/.venv/bin/python -m apps.daily_risk_scheduler.run --date 2026-10-29 --apply
```

The agent could not perform container recreation because Docker required
interactive sudo. Operator confirmation supplies the live rollout checkpoint;
the agent did not independently inspect live-dev business rows after rollout.
See [daily operations](../apps/daily_risk_scheduler/README.md) for configuration,
receipt fields, missing-ward behavior and recovery limits.
