# Scout Run Now and Scheduling Integration

Date: 2026-08-28

Updated: 2026-08-31 — recurring Scout schedules and validation.

## 1. Overview

The AnsimK Scout workbench exposes two distinct ways to run the same Scout
research implementation:

```text
Nexgent frontend Scout Workbench :5173
  |
  +-- Run Now
  |     -> POST Scout API :8091 /v1/scout/runs
  |     -> ScoutRunService
  |     -> ansimk_scout_agent
  |     -> report.md + execution.jsonl
  |
  +-- Schedule Scout
        -> Scheduling API :8092
        -> persistent SQLite schedule repository
        -> DateTrigger (Once) or Asia/Seoul CronTrigger (recurring)
        -> at the scheduled time:
             POST Scout API :8091 /v1/scout/runs
        -> persist the returned Scout result
        -> frontend reconstructs state with GET /v1/scout/schedules
```

There is still only one Scout research implementation. The Scheduling API does
not reproduce search, fetch, extraction, summarization, validation, or artifact
persistence. It records a trigger rule and later invokes the existing Scout
HTTP contract. Scout remains authoritative for its run result and timing.

## 2. Phase 1 — Authoritative Scout timing contract

A successful `POST /v1/scout/runs` response includes:

- `started_at`
- `completed_at`
- `duration_seconds`
- `source_count`

`ScoutRunService` captures `started_at` and `completed_at` as timezone-aware UTC
timestamps. It measures `duration_seconds` with a monotonic clock, so wall-clock
adjustments cannot distort the elapsed run duration. For a successful response,
`source_count` is the length of the validated `sources` array.

The terminal `run_succeeded` event in `execution.jsonl` is written with the same
authoritative start time, completion time, monotonic duration, and source count
returned by the API. Its event timestamp is explicitly the authoritative
`completed_at` value rather than a separately sampled timestamp.

While a Run Now request is pending, the frontend displays a browser-side
`Elapsed MM:SS` timer based on `Date.now()` and updated once per second. This is
only an honest indication of how long the open HTTP request has been pending;
there is no percentage or fabricated backend stage. When the request finishes,
the live timer disappears and the UI uses the backend `duration_seconds` value.
`completed_at` is formatted in `Asia/Seoul` and explicitly labeled `KST`.

The Run Now details appear in this order:

1. Status
2. Duration
3. Completed
4. Sources
5. Run ID
6. Report artifact
7. Execution log

If a later Run Now attempt fails, the previous successful report remains in the
result panel. When Scout has created a run and returns the safe HTTP 502 failure
shape, the UI shows that failed attempt's authoritative timing and log metadata
separately. Validation or readiness failures that occur before a run exists do
not fabricate a run ID, timestamps, duration, source count, or artifact.

## 3. Phase 2 — Standalone Scout Scheduling API

The standalone Scheduling API provides:

- `POST /v1/scout/schedules` — create a Once, Daily, Weekly, or Monthly schedule.
- `GET /v1/scout/schedules` — list current and terminal audit records.
- `DELETE /v1/scout/schedules/{schedule_id}` — cancel a pending schedule while
  retaining its audit record.

Supported persisted states are `pending`, `running`, `succeeded`, `failed`,
`cancelled`, and `missed`.

Every accepted schedule receives a UUID, which is also used as its APScheduler
job ID. The only supported timezone is currently `Asia/Seoul`. The client sends
`run_at` as a timezone-naive Seoul local wall-clock value such as
`2026-08-29T09:00:00` and supplies `timezone: "Asia/Seoul"` separately. The
Scheduling API validates that interpretation and rejects malformed or past
times. An exact duplicate of an existing pending schedule returns HTTP 409;
otherwise, distinct schedules coexist under distinct UUIDs.

Cancellation is a state transition, not record deletion. Only `pending`
schedules can be cancelled. A cancelled row remains in SQLite as audit history,
and running or terminal schedules return a safe conflict instead of being
removed.

The custom schedule repository and APScheduler's SQLAlchemy job store coexist
in the default SQLite database. Once uses the existing persistent `DateTrigger`.
Daily, Weekly, and Monthly use a persistent `CronTrigger` evaluated in
`Asia/Seoul`. On startup, the service reconciles persisted records and jobs:
future pending jobs are registered by UUID without creating duplicate records;
stale one-time `running` records become `failed` without a blind retry; and old
one-time pending jobs become `missed`. The default grace period is 300 seconds.

The initial APScheduler executor has one worker, so at most one Scout callback
runs at a time and simultaneous due jobs remain scheduler-managed rather than
being silently dropped. The default is configurable, but the validated setup
uses a concurrency limit of one. Exactly one Scheduling API process may own the
persistent scheduler; multi-process leader election is not implemented.

At trigger time, the callback atomically claims `pending -> running`, then calls
the existing `POST /v1/scout/runs` endpoint with the persisted topic and
keywords. The synchronous HTTP timeout defaults to 180 seconds. Successful
Scout metadata and safe Scout 502 failure metadata are validated and stored
without recomputing `started_at`, `completed_at`, `duration_seconds`, or
`source_count`. HTTP dispatch timing is operational scheduling information and
must never be presented as Scout duration. Preflight, transport, timeout, and
malformed-response failures retain safe scheduler error information without
inventing Scout metadata.

Recurring create requests omit `run_at`. They provide `schedule_time`, plus
`day_of_week` for Weekly or `day_of_month` for Monthly. A monthly rule for day
29, 30, or 31 skips months without that day, matching APScheduler cron
semantics. The response continues to expose `run_at` and `trigger_at`; for a
recurring schedule these are its next local and UTC occurrences.

After each recurring success or failure, the schedule returns to `pending` and
advances to the next occurrence. The existing result/error columns retain the
latest available execution metadata rather than a complete per-occurrence
history. Recurring missed occurrences advance without deactivating the rule.
Restart recovery does not retry an uncertain stale callback; it records the
safe recovery error and advances to the next occurrence. Cancellation remains
available whenever the recurring row is pending and retains its latest result.

Default runtime ports are:

| Component | Port |
| --- | ---: |
| Scout API | 8091 |
| Scheduling API | 8092 |
| Nexgent frontend development server | 5173 |

## 4. Phase 3 — Frontend scheduling integration

The Scout workbench at `/agents/ansimk_scout_agent` keeps **Run Now** and
**Schedule Scout** as separate actions. Both reuse the existing Topic and
optional Keywords values. Scheduling adds a Once/Daily/Weekly/Monthly selector,
the applicable date/day controls, a time control, and a visible fixed
`Asia/Seoul (KST)` label.

Daily, Weekly, and Monthly controls show the next matching execution date and
time in KST before creation. This preview is calculated only in the frontend;
it does not change scheduling logic, API payloads, or backend `CronTrigger`
behavior. Once keeps its existing date/time UI and behavior unchanged.

The frontend constructs `run_at` directly from the form fields as
`YYYY-MM-DDTHH:mm:00`. It does not pass that wall-clock value through
`Date.toISOString()` or the browser's local timezone. The Scheduling API remains
the source of truth for scheduled work.

The scheduled jobs section is reconstructed entirely from
`GET /v1/scout/schedules`. It polls every four seconds while at least one record
is `pending` or `running`, and polling stops when all returned records are
terminal. Closing or reloading the browser therefore does not discard pending,
running, completed, failed, cancelled, or missed audit state.

The UI presents honest state labels without synthetic progress. **Cancel** is
visible only for a pending record. After cancellation, the client refetches the
authoritative list and keeps the row visible as `Cancelled`; it does not delete
the row locally.

Recurring cards show the rule and next KST run. After an occurrence completes,
the card remains active, shows the latest result metadata, and continues to
offer cancellation while pending.

A succeeded scheduled run displays the authoritative Scout duration,
KST-formatted completion time, source count and links, run ID, report artifact,
execution log, and Markdown report copied through the Scheduling API. A failed
Scout run can display its safe Scout terminal metadata. A pre-run or transport
failure has no fabricated Scout timing or run metadata and instead displays the
safe scheduling error. Scheduling creation, polling, cancellation, and callback
failures never replace the latest Run Now result.

The preferred explicit LAN configuration is:

```text
VITE_SCOUT_SCHEDULER_API_BASE_URL=http://192.168.0.18:8092
```

During the canonical browser end-to-end validation, this variable was not
explicitly injected into the running Vite process. The client therefore used
its existing same-browser-host fallback, which resolved the frontend host to
`http://192.168.0.18:8092` correctly. Explicit environment configuration is
preferred for managed deployment. The URL is not hard-coded in the
application's request logic.

## 5. Persistence and artifacts

The default scheduling database is:

```text
scheduling-agent-poc/scheduling-agent/var/scout_schedules.sqlite3
```

The schedule repository tables and persistent APScheduler job-store tables use
that database. It contains scheduling state, audit transitions, safe scheduler
errors, and the Scout response metadata returned to the scheduler.

The default Scout artifacts are:

```text
adk_agents/ansimk_scout_agent/var/runs/{run_id}/report.md
adk_agents/ansimk_scout_agent/var/runs/{run_id}/execution.jsonl
```

Their responsibilities are distinct:

- SQLite stores schedule/job audit state and the returned Scout metadata.
- `report.md` is the generated, validated Scout report.
- `execution.jsonl` is the append-only Scout execution event history.

Scout artifact paths are application-controlled. User topics and keywords do
not become filesystem paths. The Scout output root and scheduling database path
are configurable, so the paths above are the validated defaults.

## 6. Runtime and supervision

Scout and the Scheduling API are installed, enabled, active, and functionally
verified under `nexgent-scout.service` and
`nexgent-scout-scheduler.service`. See
[`scout-systemd-supervision.md`](scout-systemd-supervision.md) for the installed
units, host-only environment-file strategy, operational commands, and final
verification record. The canonical bindings are:

```text
Scout API       0.0.0.0:8091
Scheduling API  0.0.0.0:8092
```

Provide runtime values through the deployment environment, an untracked local
environment loader, or an equivalent secret manager. No project-local tracked
`.env` file is assumed. Never place credentials in tracked documentation or
shell history. The following manual commands are development/fallback examples
only; do not run them while the systemd units own the canonical ports. Example
Scout startup with placeholders supplied by the runtime:

```bash
cd <ax-project-root>/nexgent/adk_agents/ansimk_scout_agent
export OPENAI_API_BASE="<internal-openai-compatible-base-url>"
export OPENAI_API_KEY="<provided-by-secret-manager>"
export SCOUT_MODEL="<internal-model-name>"
uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8091
```

The Scout environment must provide `OPENAI_API_BASE`, `OPENAI_API_KEY`, and
`SCOUT_MODEL`; values are intentionally omitted here.

Example Scheduling API startup:

```bash
cd <ax-project-root>/scheduling-agent-poc/scheduling-agent
# Load required model/runtime credentials through the deployment environment.
export SCOUT_API_BASE_URL=http://127.0.0.1:8091
export ALLOW_ORIGINS=http://192.168.0.18:5173
export INTEGRATION_TEST=TRUE
uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8092
```

`INTEGRATION_TEST=TRUE` was used for local Scheduling API startup in the
validated development environment to avoid unrelated Google ADC/cloud
telemetry dependencies. It is not required when the expected Google ADC and
cloud telemetry configuration is available. The Scheduling API's other safe
defaults include a 180-second Scout timeout, concurrency one, and a 300-second
misfire grace period.

Basic server-side checks are:

```bash
curl -fsS http://127.0.0.1:8091/health/live
curl -fsS http://127.0.0.1:8091/health/ready
curl -fsS http://127.0.0.1:8092/v1/scout/schedules
```

## 7. LAN and firewall prerequisite

Manual browser validation found an environment-level reachability issue. The
Scheduling API was healthy from the server, bound to `0.0.0.0:8092`, returning
HTTP 200, and configured with the correct frontend CORS origin, but the Mac
browser received `ERR_CONNECTION_TIMED_OUT`. UFW did not yet allow LAN traffic
to port 8092.

The applied environment fix was:

```bash
sudo ufw allow from 192.168.0.0/24 to any port 8092 proto tcp
```

The relevant LAN rules after validation were:

```text
8091/tcp ALLOW 192.168.0.0/24
8092/tcp ALLOW 192.168.0.0/24
```

These firewall rules are deployment prerequisites, not Scout, Scheduling API,
or frontend application logic. This documentation task did not make any
additional firewall changes.

## 8. Validation history

The implementation was validated in phases.

### Phase 1 — authoritative timing and Run Now

- Scout backend tests: 46 passed.
- Focused frontend tests: 18 passed.
- Full frontend suite: 164 passed.
- Frontend production build: passed.

### Phase 2 — persistent Scheduling API

- Focused Phase 2 suite: 43 passed.
- Legacy scheduler regression suite: 26 passed.
- Combined suite reached 70 passed.
- Three legacy server tests could not bind their hard-coded port 8000 because
  another existing process owned it; no existing process was stopped.
- Equivalent unchanged server behavior was validated on temporary port 18092.

### Phase 3 — scheduling workbench

- Focused frontend tests: 39 passed.
- Full frontend suite: 196 passed.
- Frontend production build: passed.
- `git diff --check`: passed.

### Phase 4 — recurring schedules (2026-08-31)

- Focused recurrence model, SQLite migration/repository, scheduler service, and
  Scheduling API tests: 68 passed.
- Focused backend Ruff format and lint checks: passed.
- Focused frontend Scout scheduling tests: 48 passed.
- All non-live Scheduling POC unit/integration tests: 95 passed. The existing
  live ADK/model integration and hard-coded-port server E2E files were excluded
  after their external boundaries did not become ready with the inert test
  environment.
- Full frontend suite: 205 passed.
- Frontend TypeScript check and production build: passed; Vite reported only
  the existing advisory for a JavaScript chunk larger than 500 kB.
- Live wall-clock execution against the real Scout service was not repeated;
  callback tests use a controlled Scout client and verify the unchanged HTTP
  contract separately.

### Canonical browser end-to-end validation

- Scout was reachable and ready on port 8091.
- The Scheduling API was reachable on port 8092.
- The Nexgent frontend ran on port 5173.
- Run Now succeeded.
- A scheduled Scout run transitioned automatically from `Pending` to `Running`
  to `Succeeded`.
- Reloading the page reconstructed the terminal scheduled result from the
  Scheduling API.
- Cancelling a second pending schedule retained its `Cancelled` audit record.
- No application-level browser console errors occurred during the canonical
  end-to-end run.
- The Scout API response, Scheduling API record, and terminal Scout JSONL event
  agreed on authoritative timing and source count.

Validation also found a stale Scout process on canonical port 8091. It had been
started before the Phase 1 timing-contract code was loaded, so it was restarted
on port 8091 before the final end-to-end run. Port 8093 was used only for an
earlier isolated validation and is not part of the current architecture or
configuration.

## 9. Known limitations and future operational work

The current Scout scheduling integration has these remaining limitations:

- no multi-process scheduler leader election;
- no schedule update or reschedule endpoint;
- no separate per-occurrence result-history table;
- no automatic retry policy;
- no Slack integration;
- one supported scheduler process owner; and
- an initial Scout callback concurrency limit of one.

These items are not implemented. Systemd now provides durable supervision for
the single Scout and Scheduling processes, while persistent SQLite and
APScheduler state continue to provide schedule reconciliation after process
restart.

## 10. Scope and history note

The Scheduling API implementation lives outside the `nexgent/` subtree but
within the same `ax-project` Git repository, at:

```text
scheduling-agent-poc/scheduling-agent/
```

This document intentionally lives with the Scout documentation because it
describes the complete end-to-end Scout capability shared by Run Now and
Schedule Scout. The standalone backend record
[`standalone-scout-agent-backend-poc.md`](standalone-scout-agent-backend-poc.md)
remains the detailed Scout backend baseline and has not been moved or rewritten.
Some older phase documents describe frontend scheduling as a future TODO; those
statements record the status at the time they were written, while this document
records the current integrated state.

## 11. Optional research guidance — 2026-08-31

Run Now and Schedule Scout now share one optional `additional_instructions`
value. The frontend trims it, omits blank values from JSON, and enforces the
2,000-character limit before calling either existing endpoint.

The Scheduling API persists normalized guidance in an additive nullable
`additional_instructions` SQLite column. Existing rows read as `null`. The
pending-schedule uniqueness index includes the nullable field through
`COALESCE`, so otherwise-identical schedules with different guidance remain
distinct. APScheduler still stores and dispatches only the schedule ID; the
callback reloads the application record and forwards its guidance to the
unchanged Scout run endpoint. Recurrence, trigger, status, recovery, and
terminal-result behavior were not changed.

The Scout backend treats the field only as subordinate role-user research
guidance. `SCOUT_INSTRUCTION`, web-tool boundaries, deterministic report/source
validation, endpoint paths, and execution logging remain unchanged.

Validation:

- focused scheduler model, migration/repository, dispatch/client, and API suite:
  73 passed;
- changed scheduler files passed Ruff;
- full frontend suite: 209 passed;
- frontend TypeScript and production build: passed with the existing Vite chunk
  size advisory; and
- the broader scheduler run reached 100 passing tests, while its unrelated live
  scheduling-agent test could not reach the inert test model endpoint and three
  server E2E tests could not bind already-occupied port 8000. No existing
  process was stopped.
