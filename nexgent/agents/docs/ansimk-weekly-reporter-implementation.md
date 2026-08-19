# Ansimk weekly reporter implementation

Date: 2026-08-18

Status: **Implemented manual reporting path**

## Outcome

`ansimk_weekly_reporter` calculates a current and previous seven-day snapshot
for each selected ward, creates a grounded qualitative fact package, asks the
configured LLM for warm Korean prose, validates it, and renders deterministic
Markdown in the guardian-facing weekly-life-report template. The spreadsheet
wording tab is a tone and safety reference only; its field names, scores, and
thresholds are not calculation rules.

## Boundaries

```text
PostgreSQL raw tables
  -> reusable read-only asyncpg pool
  -> private weekly-report FastAPI source API
  -> typed workflow-local HTTP client
  -> deterministic qualitative facts
  -> warm Korean reporter agent
  -> narrative validation or template fallback
  -> grounded Markdown and versioned result
  -> optional human-approved Slack reports destination
```

- `apps/weekly_report_api` owns the private HTTP process, health endpoints,
  database lifecycle, and safe error mapping.
- `packages/integrations` owns the reusable read-only PostgreSQL pool.
- `workflows/weekly_report/source` owns source SQL and exact calculations.
- `workflows/weekly_report/tools` owns the workflow-specific source client.
- `workflows/weekly_report/agents/reporter` owns prompt, policy, retry, and
  fallback behavior.
- `workflows/weekly_report/domain` owns qualitative fact selection and Markdown.
- `packages/integrations` also owns reusable outbound Slack transport and
  destination validation.
- `workflows/weekly_report/slack_delivery.py` owns explicit, post-generation
  delivery approval and per-report sending.
- `.agents/skills/weekly-reporter` teaches future development agents these
  boundaries without adding global configuration.

## Source and calculations

Candidate wards are the ordered union of wards with current-period daily
summaries, evaluations, or dispatch requests. Explicit ward IDs are also
supported; missing IDs are returned in `skipped`. Automatic selection returns
an opaque cursor bound to the week and timezone and never exceeds twenty-five
wards per request.

The source service reads fourteen days so both current and previous values use
raw data. It implements the verified server semantics:

- weighted environment averages using measurement counts;
- minima and maxima over stored daily extrema;
- arithmetic activity and sleep averages over non-null rows;
- linear clock-time averages;
- risk-event count for `DANGER` evaluations;
- distinct local danger dates for compatibility;
- `DANGER` to `STABLE` resolution transitions seeded from the last prior event;
- average non-null risk score without interpreting its direction;
- dispatches created in the period and their current resolution flag.

Management notes, evaluation notes, dispatch descriptions, admin history, and
raw rows never enter the model prompt.

Every source relation is schema-qualified with `ansimk`. Matching relations in
`ansimk_clone` and `archive` are not approved inputs and cannot be selected by
the connection's PostgreSQL `search_path`.

## Private API

Endpoints:

- `GET /health/live`
- `GET /health/ready`
- `POST /internal/v1/weekly-report/source`

The POST body is `WeeklyReportRequest`; the response is
`WeeklyReportSourceResponse`. Both reject unknown fields and carry
`schema_version`. The endpoint is available only on the private Compose network.

## Narrative contract

The model receives Korean qualitative facts only. It returns:

```json
{
  "headline": "따뜻한 한 문장",
  "analysis_text": "네 문장부터 여섯 문장의 주간 설명",
  "observations": ["검증된 관찰"],
  "suggestions": ["부드러운 제안"]
}
```

The analysis must be 220–420 characters. All prose must contain Korean and no
digits. The validator rejects diagnosis, emergency certainty, accident
certainty, commands, excessive certainty, duplicate items, and malformed
JSON. Invalid output receives one bounded correction attempt. Remaining model
or validation failures use a deterministic fallback and set
`generation_mode=template_fallback` with a safe reason. One complete Markdown
JSON code fence is normalized before validation; the reporter never extracts
JSON from surrounding prose or relaxes the narrative schema.
Prompt version `weekly-korean-warm-v2` asks the model to verify sentence and
character counts and provides bounded rule-specific feedback on the single
corrective retry.

Numbers are rendered only from `WardWeeklyMetrics`; generated prose is never
parsed to create calculations.

## Rendered report template

The deterministic renderer uses the following order:

1. `주간 생활 리포트` basic information and weekly summary;
2. sleep pattern, activity, indoor environment, device-data reception, and
   risk-management sections with current/prior metrics;
3. up to three guardian action suggestions, each paired with a validated
   observation as its basis.

The contract's exclusive Monday `week_end` is displayed as the inclusive
Sunday reporting date. Activity and sleep status labels describe only verified
week-over-week direction. Until product-owned rules are versioned, subscriber
status scores and environmental recommendation ranges are explicitly shown as
undefined. Signal-loss counts and risk-management notes are not present in the
source contract; the report does not invent them or expose raw management text.

## Configuration and operation

Database settings:

```text
ANSIMK_DATABASE_DSN
ANSIMK_DATABASE_MIN_POOL_SIZE
ANSIMK_DATABASE_MAX_POOL_SIZE
ANSIMK_DATABASE_CONNECT_TIMEOUT_SECONDS
ANSIMK_DATABASE_COMMAND_TIMEOUT_SECONDS
```

Workflow source-client settings:

```text
WEEKLY_REPORT_SOURCE_URL
WEEKLY_REPORT_SOURCE_TIMEOUT_SECONDS
```

Outbound Slack settings:

```text
SLACK_BOT_TOKEN
SLACK_DEFAULT_CHANNEL_ID
SLACK_REQUEST_TIMEOUT_SECONDS
```

`SLACK_CHANNEL_REPORTS` is an optional logical destination.

The first version remains manual. It does not schedule runs, write to the
source database, or persist rendered reports. An operator may send a completed
batch through the approved default or configured logical destination only after passing
the explicit sensitive-delivery confirmation. Delivery is outside the graph so
graph retries do not duplicate messages. Slack setup and the end-to-end command
are documented in `docs/slack-outbound-messaging.md`.

## Verification gates

- Contract tests cover strict request/response validation and FastAPI behavior.
- Unit tests cover weighted and linear averages, prior deltas, fact priority,
  opaque cursors, model retry, forbidden language, fallback, and progress-event
  redaction. Slack unit tests cover destination authorization, thread replies,
  blocks, rate limits, timeout, provider failures, redaction, and the weekly
  delivery approval gate without contacting Slack.
- Evaluations require sorted batches, Korean Markdown structure, identity,
  numeric grounding, narrative safety, and fallback disclosure.
- Deployment checks require Ruff, pytest, LangGraph validation, Compose config,
  and a live readiness check with operator-supplied secrets.
