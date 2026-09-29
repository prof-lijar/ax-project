# Weekly-report failure alerts

Date: 2026-09-29 (Asia/Seoul)

## Contract and acceptance criteria

The scheduler records each attempt and its current stage on the shared durable
state volume. Normal errors and termination persist a failed attempt before
trying the backend notification API. A separate monitor detects failed attempts,
lost heartbeats, excessive runtime, and missed Monday 01:00 Asia/Seoul starts.
The monitor must run independently of the scheduler and bulk API.

- Generation errors never proceed to production migration.
- Failure alerts use Korean native Slack blocks and identify the reporting week,
  stage, observed status, and known batch counts. Unknown coverage stays unknown.
- Notification retries preserve the original payload and idempotency key and
  never restart report generation or database migration.
- Abrupt scheduler death is detectable without code running in that process.
- A first monitor deployment does not manufacture historical missed-run alerts.
- No raw exception text, database credentials, or subscriber data enters alerts.

## Behavior and delivery

| Condition | Detection |
| --- | --- |
| Configuration, submission, agent generation/storage, migration, or completion-notification error | Immediate best-effort API submission after recording failure |
| Graceful process termination (SIGTERM/interrupt) | Record failure and attempt submission before exiting |
| Abrupt process death, SIGKILL, or stopped container | Last heartbeat is at least five minutes old |
| Alive process that never finishes | Attempt age reaches 27 hours |
| Cron/scheduler never started | Monday 01:15 KST with no attempt or valid migration receipt for the reporting week |

The monitor checks every 30 seconds. API submission is bounded by the shared
three-attempt adapter; accepted submissions are queued, not yet proven delivered.
The backend worker owns Slack delivery retry/status. A backend outage leaves
the event pending with 30/60/120/240/300-second retry delays. One event is
submitted per tick so a backlog or failed backend does not block detection.

Each run writes a UUID-scoped `runs/<week>.<uuid>.json` record. The notification
stage is entered only after the production migration receipt is present; its
failure message explicitly states the DB update completed but the coverage
notification did not finish. Other failure stages do not claim production
coverage. Job counts describe the last observed batch, not the whole roster.
Raw errors, command output, subscriber identities and secrets are excluded.

`alerts/<run-id>.json` holds an immutable payload, backend URL, idempotency key,
next attempt time and acceptance receipt. A missed schedule uses
`alerts/missed-<week>.json`. The first detected incident per attempt is retained,
so a heartbeat alert followed by a caught error does not create duplicates.
Manual reruns have distinct attempt IDs and can alert independently. A shared
file lock coordinates monitor and scheduler; a crash after backend acceptance
replays the same key/body. Changing backend URL while an event is pending is
rejected to avoid sending to two backends.

`monitor.json` retains the first monitor activation. The first deployment does
not alert retroactively for earlier schedules. Subsequent restarts check missed
schedules since activation (up to the most recent 53 weeks); explicit failed or
unfinished run records remain observable regardless of age. Keep terminal run
records and accepted alert receipts together when archiving. Do not delete the
activation file during normal recovery.

## Deployment and recovery

Use the existing `WEEKLY_REPORT_NOTIFICATION_ENABLED=true`, API URL, service
token and destination settings in `agents/.env`. Both processes use the same
configuration and `/var/lib/ax/weekly-report-scheduler` volume. Notification
disablement disables both completion and failure delivery. The monitor still
records its activation baseline while disabled.

From `agents/`:

```bash
docker compose -f ../compose.prod.yaml -f compose.weekly-report-monitor.prod.yaml up -d --build --no-deps weekly-report-scheduler weekly-report-monitor
```

The agents-owned overlay adds a separate monitor service with no scheduler or
bulk API startup dependency. It mounts notification configuration and shared
status storage, without the migration credentials/SSH mounts. Agent-only
`compose.yaml` also includes it in the `scheduled` profile. Production remains
the single schedule owner; do not enable development scheduling concurrently.

Inspect scheduler/monitor logs for safe failure event names and the persisted
run stage/job ID, then use the scheduler's existing per-week recovery command
when appropriate. Failure notification retry is automatic while the monitor
runs; it does not retry a failed report job. The existing completion notification
recovery procedure remains unchanged. Do not clear pending alerts to retry them.

If the monitor, shared volume or entire host is unavailable, this same-host
monitor cannot alert during that outage. Use a separately hosted observer for
host-level coverage. Backend/Slack outages also delay actual delivery; pending
failure records/events are retried after recovery. Monitor configuration/storage
failures are logged and retried, but cannot reliably report themselves through
the same broken notification/storage path.

## Verification checkpoint

Focused tests cover every pipeline failure stage, partial/failed/cancelled/expired
jobs, configuration failure, termination, success, heartbeat loss, runtime
overrun, missed-start grace, first-install/restart behavior, backend retry and
safe payload fields. An integration test kills a real child scheduler process
with SIGKILL and verifies that the independent monitor creates the alert. Each
failure reason is validated against the actual backend native-block schema.

A clearly labeled simulated generation failure was sent through the backend
Slack client to the approved `#nexgent-test` channel on 2026-09-29:
[test message](https://the-nextor.slack.com/archives/C0BUS7UJ0EP/p1790671597186449).
Its three example targets and fake job/run IDs are explicitly identified as
test data. This verifies Slack rendering, not deployment of the monitor or
end-to-end scheduled backend-queue delivery.

Changed-file Ruff, LangGraph validation (four graphs), agent-only and production
overlay Compose rendering, and the weekly-reporter skill validator passed.
Final agent regression suite: **744 passed, 25 skipped**.
The implementation has not been deployed; rebuild/start the scheduler and
monitor together using the command above to activate crash/missed-run coverage.
