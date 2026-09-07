# Weekly Report Scheduler

This private cron service submits one durable Weekly Reporter bulk job every
Monday at 03:00 in `Asia/Seoul`. The cron expression is `0 3 * * 1`.

Each run targets the previous fully completed Monday-through-Sunday period and
requests up to 10,000 reports by default. The idempotency key is derived from
that period's Monday, so a retried cron invocation resolves to the existing job
instead of creating duplicate work.

The service calls only the private bulk control API. It does not access either
PostgreSQL database, execute reports, call the model, or download generated
content. Submission retries are bounded and log content-free JSON events.

Configuration:

- `WEEKLY_REPORT_BULK_API_URL`, default
  `http://weekly-report-bulk-api:8090`;
- `WEEKLY_REPORT_SCHEDULE_MAX_REPORTS`, default `10000`;
- `WEEKLY_REPORT_SCHEDULE_TIMEOUT_SECONDS`, default `30`;
- `WEEKLY_REPORT_SCHEDULE_ATTEMPTS`, default `3`; and
- `WEEKLY_REPORT_SCHEDULE_RETRY_DELAY_SECONDS`, default `2`.

The schedule and reporting timezone are intentionally fixed to
`Asia/Seoul`. Changing the schedule requires a reviewed crontab and image
deployment; the current frontend controls do not reconfigure this service.

The stable-server Compose stack starts this service by default and is the
single automatic schedule owner. Development and agent-only Compose stacks
place it behind the `scheduled` profile to avoid duplicate weekly generation
when multiple environments share the same source, writer, or model systems.
