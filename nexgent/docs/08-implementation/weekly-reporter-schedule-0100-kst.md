# Weekly Reporter 01:00 KST Schedule

Date: 2026-09-08

The private Weekly Reporter scheduler now submits its Monday bulk job at
01:00 `Asia/Seoul` (`0 1 * * 1`) instead of 03:00. The container timezone
remains fixed to `Asia/Seoul`, so the cron time is interpreted as Korea time.

Updated the scheduler crontab, scheduler README, and unit-test expectation.
Existing idempotency and previous Monday-through-Sunday report-window logic is
unchanged.

Validation:

```bash
cd agents
UV_CACHE_DIR=/tmp/nexgent-uv-cache uv run --no-sync pytest tests/unit/test_weekly_report_scheduler.py
UV_CACHE_DIR=/tmp/nexgent-uv-cache uv run --no-sync ruff check apps/weekly_report_scheduler tests/unit/test_weekly_report_scheduler.py
```

After rebuilding the image, recreate the scheduler container so the new
crontab is installed:

```bash
docker compose -f compose.prod.yaml build weekly-report-scheduler
docker compose -f compose.prod.yaml up -d --force-recreate weekly-report-scheduler
```
