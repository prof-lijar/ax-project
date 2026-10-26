# Weekly report five-second progress logs

Date: 2026-10-26 (Asia/Seoul)

## Implementation

`wait_for_storage` now defaults to a five-second bulk-status polling interval
instead of thirty seconds. Every nonterminal iteration emits a flushed JSON
`weekly_report_schedule_progress` event with timestamp, job ID, reporting week,
generation stage, job status, discovered/completed/failed/pending/running counts,
and producer completion. Scheduled runs and manual `--regenerate` runs share
this behavior. Unchanged counts still log, making active waits visible.

Only allowlisted metadata is emitted. Subscriber details, source snapshots,
report content, and raw exception messages are excluded. After a transient
polling error the next event repeats the last observed state. HTTP request
duration adds to the five-second sleep, so this is not a strict wall-clock
heartbeat during a stalled request. Migration retains its existing start/end
events and subprocess output; this change adds generation progress logs.
Completion validation, deadlines, idempotency, and Slack notification rules
remain unchanged. Status requests are six times as frequent per waiting run.

## Validation

125 focused scheduler, pipeline, completion-notification and failure-notification
tests passed. A deterministic clock test verifies five-second waits, latest
counts, continued logs across a transient outage, and exclusion of arbitrary
job fields. Changed-file Ruff and `git diff --check` passed.

From `agents/`:

```bash
.venv/bin/pytest --disable-warnings tests/unit/test_weekly_report_schedule_pipeline.py tests/unit/test_weekly_report_scheduler.py tests/unit/test_weekly_report_completion_notification.py tests/unit/test_weekly_report_failure_notification.py
.venv/bin/ruff check apps/weekly_report_scheduler/pipeline.py tests/unit/test_weekly_report_schedule_pipeline.py
```

## Rollout and remaining verification

The production scheduler has not been rebuilt: Docker access requires
interactive sudo authentication. Do not recreate it during an active generation
or migration. Between runs, execute from `nexgent/`, retaining any production
overlay arguments used by the deployment:

```bash
sudo docker compose -f compose.prod.yaml up -d --build --no-deps weekly-report-scheduler
```

For the failed October 19 week, after also deploying the source query fix,
the following single-line command shows progress directly in the terminal and
then migrates successful generation to production and attempts notification:

```bash
sudo docker compose -f compose.prod.yaml exec -T weekly-report-scheduler /app/.venv/bin/python -m apps.weekly_report_scheduler.pipeline --week-start 2026-10-19 --regenerate device-join-v1
```

Manual `docker compose exec` output goes to that terminal; cron output goes to
the scheduler container logs. Live cadence, generation, production migration,
and Slack delivery remain to be verified by the operator. Reuse the same
regeneration key to resume; a retained terminal generation failure requires a
new key after fixing its cause.
