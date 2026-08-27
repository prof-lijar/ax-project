# Ansimk weekly reporter implementation

Date: 2026-08-24

Status: **Implemented interactive and durable bulk reporting paths**

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
- `apps/weekly_report_bulk_api` owns the private operator control plane for
  job submission, recent-job discovery, progress, cancellation, and verified
  ZIP download. It does not execute reports itself.
- `apps/workers/weekly_report.py` owns the independently scalable producer,
  consumer, and finalizer process.
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
- per-date environment departure counts after collapsing multiple device rows;
- arithmetic activity and sleep averages over non-null rows;
- weekly movement and remote-control totals over non-null rows;
- per-row good, power, and weak-position device-reception occurrence counts;
- linear clock-time averages;
- risk-event count for `DANGER` evaluations;
- distinct local danger dates for compatibility;
- `DANGER` to `STABLE` resolution transitions seeded from the last prior event;
- average non-null risk score, rendered through the approved score policy;
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
  "analysis_text": "평가 가능한 사실 중 가치 있는 주간 통찰만 자연스럽게 요약",
  "observations": ["검증된 관찰"],
  "suggestions": ["부드러운 제안"]
}
```

Production summaries review all available qualitative facts but do not require
one sentence per report area or a fixed area order. Every material CAUTION or
RISK topic is required; stable GOOD facts are optional context and may be
omitted when they do not add insight. The headline, one-to-four selected insight
sentences, and deterministic closing action produce a concise `한주 총평`.
Direct compatibility packages without an outline retain the one-to-six-sentence
fallback. All prose must contain Korean. Digits are accepted only when the same
significant token is present in the Python-owned outline. The validator rejects
invented numbers, diagnosis, emergency certainty, accident certainty, commands,
excessive certainty, unrelated missing-data filler, duplicate items, and
malformed JSON. Invalid output receives one bounded
correction attempt. Remaining model or validation failures use a deterministic
fallback made only from supplied facts and set
`generation_mode=template_fallback` with a safe reason. One complete Markdown
JSON code fence is normalized before validation; the reporter never extracts
JSON from surrounding prose or relaxes the narrative schema.
Prompt version `weekly-korean-valuable-insights-v14` assigns the model the role
of a Korean customer-support and guardian-communication expert and consumes a deterministic
`summary_outline`. Python derives valid days and data quality, selects
`ALL_GOOD`, `MIXED`, `RISK`, `LOW_DATA`, or `PARTIAL_DEVICE`, and supplies
allowlisted qualitative activity, environment, device, and closing-action
evidence. The outline headline is personalized with the validated subscriber
name and rendered as the first summary sentence. The LLM receives qualitative
movement, remote-control, temperature, humidity, and device assessments plus
exact guardian candidates, then synthesizes only the most useful grounded
insights instead of copying every block. Python-supplied data-availability
findings are valid summary evidence: when sensor values are unavailable, the
summary connects the activity, indoor-environment, and device-reception state
without inferring the subscriber's condition. The personalized headline alone
starts with and contains `지난 한 주`; analysis begins with a connector and
does not repeat that period phrase or the headline's core wording. The renderer
owns CLOSE, whose current-action line begins with `이번 주`. Low and partial modes constrain claims to the observable range.
For absent reception, CLOSE is exactly
`이번 주에는 기기 전원 연결 상태를 확인해 주시고, 생활환경을 함께 살펴봐 주세요.`
Numeric validation admits only
significant valid-day and device-issue counts already supplied by Python. Sleep
and dispatch are excluded from the fact package, narrative, observations,
suggestions, and rendered Markdown.
Every analysis sentence must naturally connect to the preceding summary text.
Urgent terms such as `빠른`, `즉시`, `위급`, and `긴급` are rejected. If
device reception is unavailable, Python adds the deterministic guardian guide
`기기 전원이 연결되어 있는지 확인해 주세요`; the summary CLOSE is never added
to model suggestions, and the renderer drops an invented time-scoped CLOSE, so
it cannot become a generic numbered action.

Numbers are rendered only from `WardWeeklyMetrics`; generated prose is never
parsed to create calculations.

## Rendered report template

The deterministic renderer uses the following order:

1. `주간 생활 리포트` basic information and `한주 총평`, which closes with a
   mode-aware deterministic action combining at most two priority checks;
2. activity, indoor environment, device-data reception, and risk-management
   sections with current/prior metrics and contiguous numbering;
3. up to three guardian action suggestions, each paired with a validated
   observation as its basis.

For approved activity RISK, environment RISK, and device CAUTION results, the
third stage uses code-owned guardian guides instead of model-authored mappings.
Each guide includes an exact internal condition, displayed title, and analysis
sentence. The condition is not rendered; the title is the card heading and the
analysis is its body. An unavailable-reception power check comes first;
otherwise guides are ordered movement, remote control, environment, then
device and capped at three. They occupy the first slots, while validated
model suggestions fill only unused slots. A separate summary policy owns the
integrated closing action for `한주 총평`. Environment hot and cold guides map
by semantic condition rather than internal environment variant number. The
source typo `롹인` is normalized to `확인`.

The basic information shows the grounded weekly-average status score and its
calm classification but omits the full score-band legend. Sleep and dispatch
are not report topics and are never rendered.

The contract's exclusive Monday `week_end` is displayed as the inclusive
Sunday reporting date. The activity section compares current and previous
weekly totals independently for movement and remote-control use. Each signal
shows its total ratio, uppercase status, exact guidance, and short summary:
`GOOD` for 70–150%, `CAUTION` for 40–70% or 150–250%, and `RISK` below 40% or
above 250%. Exactly 250% is `CAUTION`; missing totals or a zero previous total
are disclosed as unavailable. The resulting qualitative guidance may enter the
model fact package, but totals, percentages, and thresholds do not. Indoor
temperature and humidity use strict year-round product-approved ranges:
`15℃ < temperature < 31℃` and `30% < humidity < 70%`. Exact boundary values
are treated as departures. All device rows are collapsed by date, then stored
minimum and maximum temperature and humidity are
used to count range departures. Zero and one combined departure day select the
two approved `GOOD` variants. Two or three combined departure days select the
combined `CAUTION` variant; two or more single-dimension departure days remain
the applicable `CAUTION` variant unless a RISK rule applies. Directional `RISK`
uses
the daily maximum: humidity below 30% or above 70%, and temperature below 15℃
or above 31℃, repeated on four or more dates. Exactly 30%, 70%, 15℃, and 31℃
do not satisfy these strict extreme boundaries. Combined recommended-range
temperature-and-humidity departure on four or more dates selects `RISK 5`.
The renderer exposes exact approved copy, summary, counts, and extrema, while
the model receives only the qualitative description. Numeric ranges are
internal evaluation rules and are not rendered. The current week's average
`risk_score` is rounded to the nearest whole point using half-up rounding and
rendered with the product-approved `76–100 GOOD`, `26–75 CAUTION`, and
`0–25 RISK` statuses and their exact Korean guidance. The score, uppercase
status, guidance, and classification come only from deterministic Python;
the full legend is omitted, and missing or invalid values are marked unavailable
without delegating interpretation to the model.

The device-data reception section evaluates `temperature_count`,
`humidity_count`, `light_count`, `remote_control_count`, and `movement_count`
on each raw row. All five non-null/non-zero values form a good occurrence. Three
null measurement counts plus two zero activity counts form a power occurrence.
After good and power rows are excluded, any row with at least two values from 0
through 10 forms a position occurrence. The categories are mutually exclusive.
Two repeated occurrences produce `CAUTION`, with power taking weekly
precedence; `GOOD` requires every available row to be good. Unmatched partial
combinations and zero source rows remain unavailable. For a zero-source week,
the deterministic detail section displays
`기기 전원이 연결되어 있는지 확인해 주세요.` while leaving occurrence counts
unavailable rather than inventing a power event. Python renders status, exact
copy, summary, and counts; the model sees only qualitative section assessments
and exact deterministic guardian candidates.
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
target of ninety minutes. It reuses the source API's opaque cursor and a bulk
page size of one hundred. The interactive compatibility graph remains capped
at twenty-five; one durable job repeatedly advances the cursor until it reaches
its configured maximum or the source has no more eligible wards. PostgreSQL
coordinates idempotent jobs, producer and
finalizer leases, and per-ward `SKIP LOCKED` leases. Report payloads never enter
PostgreSQL or LangGraph state. The private artifact volume holds validated
input snapshots, report JSON, and a terminal ZIP containing:

- `manifest.json`, including counts, safe failures, prompt/model metadata, and
  the `reports.jsonl` checksum;
- `reports.jsonl`, one validated report contract per line;
- `reports/<ward_id>.md`, one guardian-facing Markdown report per ward.

The default development Compose stack now starts the job database, worker, and
private control API. The API is not published on a host port; the current Vite
development server proxies `/weekly-report-bulk-api` from the Weekly Reporter
UI. This is a trusted-development path, not a production authentication
boundary.

Control API endpoints:

- `GET /health/live` and `GET /health/ready`;
- `GET /v1/weekly-report/bulk/runtime`;
- `POST /v1/weekly-report/bulk/jobs`;
- `GET /v1/weekly-report/bulk/jobs` and
  `GET /v1/weekly-report/bulk/jobs/{job_id}`;
- `POST /v1/weekly-report/bulk/jobs/{job_id}/cancel`; and
- `GET /v1/weekly-report/bulk/jobs/{job_id}/export`.

Start the complete development stack with:

```bash
cd /home/nextor-ai-02/nextor_ai/ax-project/nexgent
sudo docker compose up --build -d
sudo docker compose logs -f weekly-report-worker weekly-report-bulk-api
```

Open `/agents/1`, choose **Bulk generation**, approve the live private-model
run, and start with 100–1,000 reports before attempting 10,000. The UI polls
content-free status, shows discovered/queued/running/completed/fallback/failed
counts, observed reports per second, projected finish, recent durable jobs,
in-flight cancellation, and the terminal ZIP download. Cancel and stop-and-refresh
persist a cancellation request; page refresh and navigation send the same
request with browser keepalive. The worker cancels active model awaits and
marks every pending or leased item cancelled, while preserving reports that
completed before the stop request.

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
The runner also terminalizes producer, consumer, and finalizer exceptions so a
failed oldest job cannot remain active and block every later job. Individual
model calls use `WEEKLY_REPORT_ITEM_TIMEOUT_SECONDS` (default 60 seconds); a
timeout produces the normal grounded template fallback for that ward while the
batch continues. The worker catches terminal job failures and returns to its
poll loop. Export responses send the verified ZIP in bounded chunks.
The response advertises the verified artifact's actual byte size; initializing
the stream with an empty response must never leave `Content-Length: 0`, because
browsers may then save a zero-byte download even when the streamed body exists.
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

The configured worker concurrency (32 by default) is an application-side upper
bound, not a guarantee of 32 simultaneous GPU sequences. The inference server
still owns continuous batching and admission. When bulk and Chat share one
model endpoint, a load run can increase Chat latency; production must reserve
interactive inference capacity or use a separate bulk endpoint. The UI requires
explicit confirmation and displays this limitation before submission.

## Verification gates

- Contract tests cover strict request/response validation and FastAPI behavior.
- Unit tests cover weighted and linear averages, daily-extrema environment
  counts, classification precedence, and exact feedback; risk-score rounding
  and band boundaries; device-reception overlap, precedence, and exact copy; conditional
  deterministic guardian-guide copy, semantic mapping, priority, cap, and rendering;
  report-topic exclusion and section numbering, warm summary suggestions, prior deltas,
  fact priority, opaque cursors, model retry,
  forbidden language, fallback, and progress-event redaction. Slack unit tests
  cover destination authorization, thread replies,
  blocks, rate limits, timeout, provider failures, redaction, and the weekly
  delivery approval gate without contacting Slack.
- Evaluations require sorted batches, Korean Markdown structure, identity,
  numeric grounding, narrative safety, fallback disclosure, and explicit bulk
  two-hour/ninety-minute capacity projections.
- Bulk unit and contract tests cover idempotent submission, leased claims,
  atomic private artifacts, manifest/JSONL/Markdown export, safe partial
  failure, cancellation, recent-job ordering, private control API validation,
  checksum-verified download, non-zero response length, and lease recovery. A PostgreSQL-backed
  integration run and a representative 10,000-report model benchmark remain
  deployment release gates.
- Deployment checks require Ruff, pytest, LangGraph validation, Compose config,
  and a live readiness check with operator-supplied secrets.
