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
Prompt version `weekly-korean-warm-v3` asks the model to verify sentence and
character counts, requires a supplied indoor-environment status in the weekly
analysis, and provides bounded rule-specific feedback on the single corrective
retry.

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
week-over-week direction. Indoor temperature uses a product-approved range
selected from the reporting week's starting month: 18–20℃ in January–March and
November–December, 20–22℃ in April–May and October, and 26–28℃ in
June–September. Humidity uses 40–60% throughout the year. Weekly extrema below
or above those bounds produce cold/hot or dry/humid qualitative facts that the
weekly analysis must mention. Subscriber status scores remain undefined.
Signal-loss counts and risk-management notes are not present in the source
contract; the report does not invent them or expose raw management text.

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

Both report paths remain manually triggered and never write to the source
database. The interactive graph does not persist rendered reports. The bulk
worker stores temporary private artifacts for seven days solely to support
resume and export. An operator may send a completed interactive batch through
the approved default or configured logical destination only after passing the
explicit sensitive-delivery confirmation. Bulk Slack delivery is not
implemented. Delivery remains outside generation so retries cannot duplicate
messages. Slack setup is documented in `docs/slack-outbound-messaging.md`.

## Concurrent interactive Chat

The frontend treats normal Chat and a live Weekly Reporter run as independent
bounded request lanes. One request of each type may run concurrently, with
separate cancellation, loading, error, and notice state. The report appears as
background work and does not disable the Chat composer. This changes only
client-side ownership: both paths may still share an inference endpoint, so
bulk worker concurrency must be benchmarked and interactive capacity reserved
when necessary.

## Bulk jobs: operation and recovery

The bulk path targets 10,000 LLM-first reports in two hours, with a healthy
target of ninety minutes. It reuses the source API's opaque cursor and maximum
page size of twenty-five. PostgreSQL coordinates idempotent jobs, producer and
finalizer leases, and per-ward `SKIP LOCKED` leases. Report payloads never enter
PostgreSQL or LangGraph state. The private artifact volume holds validated
input snapshots, report JSON, and a terminal ZIP containing:

- `manifest.json`, including counts, safe failures, prompt/model metadata, and
  the `reports.jsonl` checksum;
- `reports.jsonl`, one validated report contract per line;
- `reports/<ward_id>.md`, one guardian-facing Markdown report per ward.

Start the development dependencies and worker with:

```bash
docker compose --profile bulk up -d weekly-report-jobs-db weekly-report-api weekly-report-worker
```

The same CLI can run on an operator host configured with
`WEEKLY_REPORT_JOB_DATABASE_DSN`, `WEEKLY_REPORT_ARTIFACT_ROOT`, source, and
model settings:

```bash
uv run python -m apps.workers.weekly_report submit \
  --week-start 2026-08-17 --idempotency-key weekly-2026-08-17
uv run python -m apps.workers.weekly_report status <job-id>
uv run python -m apps.workers.weekly_report run <job-id> --concurrency 32
uv run python -m apps.workers.weekly_report export <job-id> ./weekly-reports.zip
uv run python -m apps.workers.weekly_report cancel <job-id>
uv run python -m apps.workers.weekly_report cleanup
uv run python -m apps.workers.weekly_report capacity \
  --reports 1000 --elapsed-seconds 600
```

Multiple `serve` containers may share one PostgreSQL database and artifact
volume. They all select the oldest active job, so later jobs remain queued in
the first release. Expired producer, item, and finalizer leases are reclaimed.
Completed items are immutable and idempotent; a process restart continues from
the last committed source cursor. Cancellation stops discovery, marks unstarted
or leased items cancelled, and still produces a manifest for completed work.

Use a representative model-backed load run to measure end-to-end reports per
second. The release evaluator requires at least 1.389 reports/second for the
two-hour SLA and 1.852 reports/second for ninety-minute headroom. Raise bounded
worker concurrency until the source or inference service saturates. If the
healthy gate still fails, add private OpenAI-compatible/vLLM replicas behind a
load-balanced endpoint; do not compensate with unbounded tasks or Python
threads. Keep vLLM structured output and prefix caching enabled only after the
deployed model/version passes the narrative quality evaluation.

## Verification gates

- Contract tests cover strict request/response validation and FastAPI behavior.
- Unit tests cover weighted and linear averages, prior deltas, fact priority,
  opaque cursors, model retry, forbidden language, fallback, and progress-event
  redaction. Slack unit tests cover destination authorization, thread replies,
  blocks, rate limits, timeout, provider failures, redaction, and the weekly
  delivery approval gate without contacting Slack.
- Evaluations require sorted batches, Korean Markdown structure, identity,
  numeric grounding, narrative safety, fallback disclosure, and explicit bulk
  two-hour/ninety-minute capacity projections.
- Bulk unit and contract tests cover idempotent submission, leased claims,
  atomic private artifacts, manifest/JSONL/Markdown export, safe partial
  failure, cancellation, and lease recovery. A PostgreSQL-backed integration
  run and a representative 10,000-report model benchmark remain deployment
  release gates.
- Deployment checks require Ruff, pytest, LangGraph validation, Compose config,
  and a live readiness check with operator-supplied secrets.
