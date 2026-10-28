# Unified agent environment

All configuration for processes and tools under `agents/` belongs in the ignored
`agents/.env`. The committed root `.env.example` lists supported keys. Nested
playground/infra env files and external sync env files are no longer read. Their
existing private contents are left untouched. Backend processes outside this
workspace continue to use their own deployment configuration.

## Loading and precedence

LangGraph uses the root file through `langgraph.json`. Compose supplies the same
file through service environment settings or a read-only `/app/.env` mount for
cron. Python migration tools resolve the file relative to their workspace root,
independent of the current directory. They parse it as data, never shell code.
Exported process settings take precedence for migration/database connections;
Compose may override service addresses for its network topology. Agent
notification clients read only the unified file for their enable flag, service
token and channel aliases, with no backend env fallback.

For local apps or workers that consume process environment directly, run from
`agents/` with the explicit unified file:

```bash
uv run --env-file .env python -m apps.workers.weekly_report --help
```

## Connections

| Consumer | Settings in agents/.env |
| --- | --- |
| Weekly-report source | `ANSIMK_DATABASE_DSN` |
| Weekly-report local writer | `WEEKLY_REPORT_STORAGE_DATABASE_DSN` with existing source fallback |
| Manual/scheduled migration source | `SOURCE_DATABASE_DSN`, then storage DSN, then source DSN |
| Scheduled production migration and correction tools | `LIVE_PROD_DB_*`, `LIVE_PROD_SSH_*`, `LIVE_PROD_TUNNEL_PORT` |
| Manual development migration | `LIVE_DEV_DB_*`, `LIVE_DEV_SSH_*` |
| Optional outbox delivery worker | `WEEKLY_REPORT_SYNC_LOCAL_DSN`, `WEEKLY_REPORT_SYNC_TARGET_DSN`; production overlay still required |
| Notification clients | `NEXGENT_SLACK_ENABLED`, `NEXGENT_NOTIFICATION_SERVICE_TOKEN`, `NEXGENT_SLACK_CHANNELS` |

`LIVE_PROD_DB_HOST` is the remote PostgreSQL hostname. `LIVE_PROD_DB_PORT`
defaults to 5432. Wrappers forward a loopback listener at
`127.0.0.1:LIVE_PROD_TUNNEL_PORT` (default 15432) through the configured SSH
server. Python connects to that listener with the production database
credentials. The destination hostname is no longer hardcoded. Existing
`TARGET_DB_*` and unprefixed `SSH_*` migration settings are retired.

Agent notification tokens must match the backend service token, and aliases
must exist in the backend mapping. Daily risk notifications use `daily_risk`
(`C0C24T2124E`); weekly notifications use `default`. The backend remains the
durable Slack queue and sender. The unified file was supplemented only with
missing notification client settings from the existing backend configuration;
existing user-defined values were preserved.

The optional production sync overlay reads `agents/.env` as its env file and
uses `LIVE_PROD_*` for SSH routing. Its key-based tunnel still requires a key,
known-hosts and PostgreSQL CA file. File paths belong in the unified env; the
key/certificate bytes stay in their existing files. Unifying configuration does
not automatically enable outbox enqueue or deploy its workers.

## Deployment checkpoint

Update (2026-10-28): the user explicitly approved the production daily-risk
scheduler mount. Its parent Compose service now mounts `agents/.env` read-only
at `/app/.env`, and Compose validation passed. Rebuild/recreation could not run
because `sudo -n` requires interactive authentication; the operator must run the
recreation command. The remaining patch contains only development scheduler
and production weekly scheduler changes, which remain pending.

The original checkpoint below records the broader unification rollout:

Workspace code and Compose files have been updated. Parent Nexgent
`compose.yaml` and `compose.prod.yaml` changes remain pending approval because
automatic review rejected changing scheduler secret mounts. The exact proposed
changes are in [the parent Compose patch](unified-env-parent-compose.patch).
It updates only the daily/weekly scheduler services: root env injection/mounts,
removal of nested migration and backend notification env mounts, and retention
of existing schedule/topology settings. No container has been rebuilt or
restarted, and no generation, migration or Slack message was triggered.

After the parent patch is approved and applied, rebuild/recreate the relevant
schedulers and any monitor between jobs. From `nexgent/`, use
`--env-file agents/.env` when invoking overlays that interpolate unified keys.
Cron readers need `/app/.env` available at runtime; the file is excluded from
Docker build contexts and must never be baked into images. Settings supplied
with Compose `env_file` require container recreation to pick up later changes.

Validation: 274 focused tests passed; 11 database-dependent cases were skipped.
Ruff, shell syntax, LangGraph (four graphs), skill metadata and Compose rendering
passed. The proposed parent manifests pass all three notification deployment
contracts in an isolated temporary tree. The current parent manifests still
fail two deployment contracts until approval/application. A full-suite attempt
was interrupted after it stopped making progress; no full-suite pass is claimed.
