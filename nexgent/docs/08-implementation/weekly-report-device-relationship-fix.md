# Weekly report device relationship fix

Date: 2026-10-26 (Asia/Seoul)

## Failure and verified schema

The October 26 01:00 KST run for the week starting October 19 failed during
source discovery. Job `cc3429a7-cc0d-47db-a79b-13e865e75b84` exhausted three
HTTP 503 responses, completed zero reports, and did not reach migration.
The October 23 eligibility change referenced a nonexistent physical
`ansimk.resources_ward.has_device` column. A read-only check against the
configured source database reproduced `UndefinedColumnError`, SQLSTATE `42703`.
The API converts database errors to 503; readiness only checks `SELECT 1`, so
successful readiness checks did not detect this query failure.

Schema metadata and foreign keys confirm the actual relationship:

```text
ansimk.resources_device.location_id -> ansimk.resources_location.id
ansimk.resources_location.ward_id -> ansimk.resources_ward.id
```

## Implementation

`source/queries.py` defines a shared correlated `EXISTS` expression over the
location/device join. Discovery filters with it before pagination; explicit
selection derives `has_device` as a result alias so the existing `no_device`
skip contract remains intact. Completion coverage uses its negation to count
skipped wards consistently for both weeks. No database schema migration is needed.

A ward needs at least one linked device. Multiple locations or devices never
duplicate wards or inflate coverage. A location with no device, no location,
or a device with no location does not establish eligibility. Linked devices
remain eligible even when `is_disconnected` is true; reception problems belong
in the report. Eligible wards without observations still receive no-data reports.
The earlier documentation's physical-column and null-flag assumptions are
superseded by this relationship rule.

The source and production coverage roles need SELECT access to ward columns,
location `id`/`ward_id`, and device `location_id`, in addition to their existing
report/analysis permissions. Production coverage permissions were subsequently
checked read-only as recorded below.

## Validation

- 137 focused tests passed across repository, source API, bulk execution,
  scheduling, and completion notifications. Thread-based tests stalled under
  sandbox restrictions and passed with local socket access enabled.
- One read-only PostgreSQL coverage fixture test passed. Fixtures use actual
  ward/location/device shapes, multiple devices and locations, missing links,
  and duplicate historical reports, without creating tables or writing data.
- SQLite repository fixtures no longer invent a physical `has_device` column.
  Tests execute discovery and explicit-selection SQL and check pagination,
  no-data wards, offline linked devices, and `no_device` versus `not_found`.
- Live read-only checks against the configured source database reproduced the
  original missing-column error, built a corrected one-ward source response,
  executed corrected explicit selection, and collected two-week coverage.
  No model calls, report writes, or notifications were performed.
- Changed Python files passed Ruff; `git diff --check` passed.

From `agents/`, reproduce the focused offline checks:

```bash
.venv/bin/pytest --disable-warnings tests/unit/test_weekly_report_bulk.py tests/unit/test_weekly_report_schedule_pipeline.py tests/unit/test_weekly_report_scheduler.py tests/unit/test_weekly_report_repository.py tests/unit/test_weekly_report_completion_notification.py tests/contract/test_weekly_report_api.py
```

For the read-only CTE fixture check, set `WEEKLY_REPORT_TEST_DATABASE_DSN` to an
approved PostgreSQL test connection, then run:

```bash
.venv/bin/pytest --disable-warnings tests/integration/test_weekly_report_notification_postgres.py
```

## Deployment and recovery still required

Production containers were not rebuilt or restarted: this session cannot
access the Docker socket and sudo requires interactive authentication. End-to-end
generation, production migration, and notification delivery remain unverified.
After active jobs have finished, run from `nexgent/`:

```bash
sudo docker compose -f compose.prod.yaml up -d --build --no-deps weekly-report-api weekly-report-worker weekly-report-scheduler
```

If operating with additional production overlays, retain those same `-f`
arguments, including the monitor overlay when applicable. Deploying the shared
coverage change requires rebuilding the scheduler, not just the source API.

After deployment and production-role permission verification, recover the
failed October 19 reporting week with a fresh regeneration key:

```bash
sudo docker compose -f compose.prod.yaml exec -T weekly-report-scheduler /app/.venv/bin/python -m apps.weekly_report_scheduler.pipeline --week-start 2026-10-19 --regenerate device-join-v1
```

This command generates reports, stores them locally, then upserts production
reports and attempts the configured completion notification. It is an operator
recovery command, not part of the read-only validation already performed.
The ordinary cron key retains the failed job; simply rerunning without
`--regenerate` does not repair it. Reuse the regeneration key to resume an
interrupted migration; if its generation fails terminally, fix the cause and
use a new key. Verify scheduler terminal events, the regeneration receipt,
production coverage, and notification delivery after recovery. Existing frozen
notification payloads/receipts retain their existing delivery semantics.

## Production coverage permission diagnosis (2026-10-26)

Operator logs confirm regeneration job
`ac1ae9fd-e755-4522-8ff8-44374ede4366` committed all 6,295 reports to production
and saved its migration receipt. The subsequent coverage export failed before
completion notification submission. This does not roll back report migration.

A live read-only check through a temporary SSH tunnel connected as the configured
production role, `report_operator`. `has_column_privilege` confirmed SELECT on
ward `id`/`address` and report `ward_id`/`week_start_date`, but no SELECT on
location `id`/`ward_id` or device `location_id`. Executing the actual coverage
query reproduced `permission denied for table resources_location`, SQLSTATE
`42501`. The temporary tunnel was closed. No grants, report changes, or
notifications were performed during this check.

As the production table owner or a role authorized to grant access, apply:

```sql
GRANT SELECT (id, ward_id) ON TABLE ansimk.resources_location TO report_operator;
GRANT SELECT (location_id) ON TABLE ansimk.resources_device TO report_operator;
```

Then repeat the same recovery command, retaining `--regenerate device-join-v1`.
The existing regeneration migration receipt skips submission and migration;
the pipeline resumes the pending coverage/notification step. Do not use a new
regeneration key for this notification-only recovery. Permission changes and
successful completion-notification delivery remain operator verification steps.
