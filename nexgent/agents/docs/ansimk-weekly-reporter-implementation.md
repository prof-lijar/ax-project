# Ansimk weekly reporter implementation

Date: 2026-08-24

Status: **Implemented backend compatibility graph and durable bulk reporting**

## Update: selective database recovery (2026-09-08)

Operator recovery supports `--write --skip-not-null`: bounded batch savepoints
fall back to individual row savepoints only for NOT NULL violations (23502).
Valid rows commit together; other errors still roll back. Output identifies
skipped ward IDs and columns; exit code 2 indicates skipped rows, including
all-skipped runs. Regular bulk finalization retains atomic storage. See
[database recovery](weekly-report-database-recovery.md) for commands and status
semantics. No source/model calls or queue status changes occur in recovery.

## Update: Fixed Weekly Cron Scheduler

Date: 2026-09-04

`apps/weekly_report_scheduler` is a new independently deployable cron service.
Its container timezone is fixed to `Asia/Seoul`, and BusyBox cron executes the
submission command with `0 3 * * 1`: every Monday at 03:00 KST. The command
selects the previous fully completed Monday-through-Sunday reporting period
and submits a maximum 10,000-report job to the existing private bulk API.

The idempotency key `cron-weekly-report-<week_start>` makes bounded transient
retries safe and prevents duplicate jobs for the same reporting week. The
response is size-limited and checked for a valid job ID, state, and matching
week. Structured logs contain only content-free attempt, status, week, and job
metadata. The scheduler has no database credentials and neither generates
reports nor calls the model itself.

The stable-server Compose topology starts the service by default and owns the
automatic schedule. Agent-only and complete development topologies include it
behind the opt-in `scheduled` profile, preventing duplicate weekly generation
when environments share external source, writer, or model systems. Every
enabled scheduler waits for the private bulk API to become healthy. Existing
manual bulk controls remain unchanged. Cron does not provide a durable
missed-run ledger: after all bounded delivery attempts fail, an operator must
submit that week manually.

The page schedule card now labels the configured server-cron default. Its weekday,
time, and enabled interactions remain local UI previews, and Save remains
disabled; changing the card does not reconfigure the fixed cron service.

Validation completed on 2026-09-04:

```text
Scheduler/API/deployment focused tests      14 passed
Agent test suite                            361 passed, 1 optional skip
Scheduler-focused Ruff                       passed
Frontend Vitest suite                       203 passed (20 files)
TypeScript/Vite production build             passed
LangGraph configuration                      valid, 4 graphs found
Agent/development/stable Compose rendering   passed
Project skill validation                     passed
Scheduler image build                        blocked: Docker socket permission
```

The repository-wide Ruff command also ran. It is currently blocked by two
pre-existing import/export ordering findings in `ax_integrations.__init__` and
`test_rag_chat_graph.py`; neither file is part of this scheduler change.

## Update: Frontend Bulk-Only Workflow

Date: 2026-09-04

The first-party frontend now exposes Weekly Reporter only through the durable
bulk control plane at `/agents/1`. Quick Preview, interactive per-ward report
review, the Chat-triggered reporter run, the `/test-agent` sidebar route, and
the frontend Agent Server SSE parser/types for `ansimk_weekly_reporter` were
removed. `/test-agent` redirects to `/agents/1` for old bookmarks. The catalog
keeps Weekly Reporter visible but marks it as non-Chat-capable.

The bulk browser client remains responsible for job submission, content-free
status polling, recent-job selection, cancellation, and verified ZIP download.
The registered LangGraph workflow remains available as a backend compatibility
surface and continues to be covered by backend tests; this change does not
remove or alter its source, calculation, rendering, or Slack boundaries.

Validation completed on 2026-09-04:

```text
Frontend Vitest suite                       202 passed (20 files)
TypeScript/Vite production build            passed
Tauri cargo check                           passed
npm audit --audit-level=moderate            0 vulnerabilities
LangGraph configuration                     valid, 4 graphs found
Root development Compose rendering          passed
Git whitespace validation                   passed
```

## Update: Report Storage Table Rename

Date: 2026-09-04

The approved durable frontend JSON target is now
`ansimk.resources_ward_weekly_report`. The bulk writer UPSERT, canonical schema
migration, contract test, workflow documentation, and project-local source
contract use the new name. This supersedes the original
`ansimk.ward_weekly_report` name recorded in the 2026-09-03 storage
implementation below; columns, foreign key, unique ward/week key, transaction
behavior, and stored `template_data` are unchanged.

Validation completed on 2026-09-04:

```text
Focused storage tests                         4 passed
Targeted Ruff                                passed
LangGraph configuration                      valid, 4 graphs found
Root development Compose rendering           passed
Root production-server Compose rendering     passed
Standalone Agent Server Compose rendering    passed
Weekly Reporter skill validation             passed
Git whitespace validation                    passed
```

The complete 351-test agent suite reached the unrelated
`test_reader_builds_delimited_document_content` attachment-reader test after
39 results and then exceeded a 90-second diagnostic timeout. Full Ruff also
reported two pre-existing ordering findings in
`packages/integrations/src/ax_integrations/__init__.py` and
`tests/unit/test_rag_chat_graph.py`; neither file is part of this table rename.

No live storage query or write was performed against the configured database.
After supplying the writer DSN, the remaining read-only deployment check is:

```bash
psql "$WEEKLY_REPORT_STORAGE_DATABASE_DSN" --no-psqlrc --tuples-only \
  --command "SELECT to_regclass('ansimk.resources_ward_weekly_report');"
```

It must return `ansimk.resources_ward_weekly_report` before restarting a bulk
worker with this code.

## Update: Concurrent Bulk Job Admission

Date: 2026-09-04

The `serve` worker now admits up to four distinct bulk jobs concurrently instead
of awaiting the oldest job to completion. The limit is configurable with
`WEEKLY_REPORT_ACTIVE_JOB_LIMIT`. A single process-wide semaphore preserves
`WEEKLY_REPORT_WORKER_CONCURRENCY` as the aggregate ceiling across all admitted
jobs, and the scheduler excludes its active job IDs when selecting the next
oldest job. Per-job producer, item, finalizer, cancellation, and terminal-failure
boundaries remain unchanged.

Validation completed:

```text
Focused bulk/runtime/contract tests            18 passed
Suite excluding two Chat attachment test modules 336 passed, 1 skipped
Targeted Ruff                                  passed
LangGraph configuration                        valid, 4 graphs found
Development and standalone Compose rendering   passed
Git whitespace validation                      passed
```

The unfiltered suite still stalls in an existing Chat attachment graph test, and
full Ruff still reports the two unrelated pre-existing import-order findings
listed in the storage-table update above. No live worker was rebuilt because
the pending storage-table change requires its documented database migration
check before restart.

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

Prompt version `weekly-korean-free-summary-v28` receives validated,
report-facing weekly data and returns the complete `한주 총평` as plain Korean
body text. The payload contains the subscriber name as summary identity and
deterministic `생활 활동`, `생활 패턴`, `실내 환경`, and `기기 상태`
results and approved guardian actions. It does
not contain raw rows, totals, ratios, thresholds, dates, measurements, sleep or
dispatch fields, `summary_outline`, `required_topics`, or a Python-selected
activity-combination sentence. Report `기본 정보`, overall score-band,
risk-management, and separate-record data are not part of the summary payload.

The model starts with `지난 한 주 [이름]님은`, places the core activity and
everyday lifestyle-pattern flow in that first sentence, and then connects
indoor environment, device state, and a grounded close as one short paragraph. It should sound like an
experienced guardian-support adviser, not a field list or machine-generated
report. Missing and incomparable data remain limitations rather than abnormal
conditions, and the model may not invent causes, diagnoses, risks, or actions.
It must synthesize related findings, state each fact once, and merge
same-purpose actions. Sparse reports remain concise rather than adding generic
reassurance.

Overall score-band status is not a safety determination, and device reception
is only the reliability of incoming information. Risk management and separate
records are omitted from the model payload and summary in every case; the
deterministic detail section is unchanged. Any attention signal prevents a contradictory
`평소처럼 지켜봐 주세요` close; the summary instead uses a relevant approved
action once.

The writer persona is an experienced customer-support adviser describing a
parent living alone to an adult child who lives apart. It says `활동` and
`TV 이용 등 일상적인 생활 패턴`, never `TV 이용 시간`. All observations
precede one consolidated final action sentence. Validation rejects emotional
directions such as `다정하게`, action requests before the last sentence, and
new facts added after an action.

Normal summaries use two to four sentences and reject a sequence of short
single-fact section copies. Related GOOD activity/pattern findings and related
GOOD device/environment findings are combined. For summary presentation only,
an underscore after a bracketed service label is normalized to a space; stored
identity and the deterministic basic-information section are unchanged.

The fixed opening already carries the topic particle in `[이름]님은`, so its
first clause may not immediately repeat `은/는` with `활동은`, `생활 활동은`,
or `생활 패턴은`. It uses an `이/가` subject form such as `활동이`; later
contrastive topic particles are still allowed. Validation sends a specific
bounded correction for this defect, and fallback wording follows the same rule.

When the subscriber has a usable supplied name, validation requires that name
in the opening and rejects generic substitute honorifics in later references.
For deterministic complete lifestyle-information reception absence
(`기기 상태: 자료 없음`), the prompt omits all other report areas and provides
only the subscriber, reception absence, and power check. Validation requires
the approved two-sentence copy and rejects generic overall-state or unrelated
sensor interpretation.

Validation requires one body-only Korean paragraph in warm `해요체`. It rejects
titles, labels, Markdown, line breaks, every digit, `움직임`, `리모컨`, `GOOD`,
`CAUTION`, `RISK`, formal administrative endings, excluded topics, urgent
terms, unsupported claims, and omission of any material deterministic
CAUTION/RISK area. It also rejects all risk-management references, repeated
sentences, repeated check-in intent, unsupported safety reassurance, a stable
close that conflicts with an attention signal, persona-misaligned wording,
actions before the final sentence, and new facts after an action, plus `위험`,
rushed or alarm-amplifying words, and exclamation marks. Invalid output receives
one bounded correction attempt. Remaining model or validation failures use a
disclosed deterministic fallback built from the same report-facing section
descriptions with duplicated local actions removed.

Guardian action-card titles use the 2026-09-01 observation-style copy:
`평소와 비슷하게 지내셨어요`, activity/pattern increase or decrease, the
applicable environment statement, or the device check-needed statement.
Directional environment variants one through four select the same
`ENV_CAUTION_01` through `ENV_CAUTION_04` card for either CAUTION or RISK;
combined variants five through eight remain RISK-only. Card titles supplied to
the summary prompt are qualitative headings rather than action requests, so
the model and deterministic fallback ground their closing check in verified
section descriptions.

`WeeklyNarrative` remains the versioned compatibility contract. Python splits
the first validated sentence into `headline` and stores the remainder in
`analysis_text`; `observations` and model `suggestions` are empty. The renderer
joins the two text fields with one space, preserving the exact model-authored
paragraph. Deterministic guardian action cards remain separate. A zero-source
device week keeps its approved power-check guide; an unmatched received-row
combination does not create one.

Numbers are rendered only from `WardWeeklyMetrics`; generated prose is never
parsed to create calculations.

## Rendered report template

The deterministic renderer uses the following order:

1. `주간 생활 리포트` basic information and `한주 총평`, where practical
   guidance appears beside the finding that supports it;
2. one `생활 활동` section containing `활동감지` and `리모컨 이용`, followed by
   indoor environment, device-data reception, and risk management, with no
   numbering on any main detail heading;
3. up to three deterministic guardian action cards, each with its approved
   description, tag, and supplied template ID.

For the approved activity, environment, and device statuses, the third stage
uses code-owned guardian guides instead of model-authored mappings. Each guide
includes an exact internal condition, displayed title, description, tag, and
optional template ID. The condition is not rendered; the remaining approved
fields form the action card. An unavailable-reception power check comes first;
otherwise guides are ordered device, movement, remote control, then environment
and capped at three. Model suggestions do not fill unused rendered slots
because they have no approved tag or template ID. A separate summary policy
owns the integrated closing action for `한주 총평`. Increase actions apply only
to CAUTION, while decrease actions use the specified RISK mappings.

The basic information shows the grounded weekly-average status score and its
calm classification but omits the full score-band legend. Sleep and dispatch
are not report topics and are never rendered.

The contract's exclusive Monday `week_end` is displayed as the inclusive
Sunday reporting date. The `활동감지` and `리모컨 이용` children compare current
and previous weekly totals independently. Each child shows its uppercase
status and metric values. Their exact guidance is combined once at the parent,
where one `태그` uses the worse status and its approved short summary:
`GOOD` for 70% up to but not including 150%, `CAUTION` for 40% up to 70% or
150% through 250%, and `RISK` below 40% or above 250%. Exactly 150% and 250%
are `CAUTION`; missing totals or a zero previous total
are disclosed as unavailable. The resulting qualitative guidance may enter the
model fact package, but totals, percentages, and thresholds do not. Indoor
temperature and humidity use inclusive year-round product-approved ranges:
`15℃ ≤ daily maximum temperature ≤ 31℃` and
`30% ≤ daily maximum humidity ≤ 70%`. Exact boundary values remain inside the
recommended range. All device rows are collapsed by date, then the highest
stored maximum temperature and humidity on each date are used to count range
departures. Zero or one departure day selects `GOOD`; two or three repeated
directional departure days select `CAUTION`; four or more select `RISK`.
Combined variants require both explicitly stated directional counters to meet
the threshold. The cool-humid CAUTION variant uses maximum temperature below
18℃, and the cold-humid RISK variant uses maximum humidity at or above 70%.
The private snapshot adds optional `cool_temperature_days` and
`humidity_at_or_above_70_days` counters while retaining compatibility with
older snapshots that omit them.
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
on each raw device-day row. At least two numeric counts in 0–10 inclusive
form a position occurrence, including rows with all-positive counts. Check
position first, then power (null temperature, humidity, and light), then good
(non-null/non-zero temperature, humidity, light, and movement). Null values
do not count as low. These categories remain mutually exclusive. The position
result uses `일부 생활 정보가 적게 들어온 날이 있었어요. 기기가 제자리에 있는지 확인해 주세요.`
and tag `위치 확인`.
Two repeated occurrences produce `CAUTION`, with power taking weekly
precedence; otherwise one or more good occurrences produce `GOOD`. Good
occurrences do not need to equal every source row. Unmatched rows are rendered
as `기타 수신 패턴` and do not override a matched weekly status. If source rows
exist but no weekly rule matches, the section says `판정 불가` without a power
claim. For a zero-source week,
the deterministic detail section displays
`기기 전원이 연결되어 있는지 확인해 주세요.` while leaving occurrence counts
unavailable rather than inventing a power event. Python renders status, exact
copy, summary, and counts; the model sees only qualitative section assessments
and exact deterministic guardian candidates.
Signal-loss counts and risk-management notes are not present in the source
contract; the report does not invent them, expose raw management text, or
render an empty `위험 관리 기록` placeholder subsection.

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

## Frontend execution boundary

The frontend no longer starts the interactive Weekly Reporter graph from Chat
or the agent page. Normal Chat owns one cancellable request, while Weekly
Reporter jobs run only through the independently scalable durable bulk worker.
Both services may still share an inference endpoint, so bulk worker concurrency
must be benchmarked and interactive capacity reserved when necessary.

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
- `reports/<ward_id>.md`, one guardian-facing Markdown report per ward; and
- `json/<ward_id>.json`, one frontend-ready `template_data` object per ward.

`WardWeeklyReport` retains the existing `markdown` field and also generates
`template_data` with template version `weekly-report-v5`. Its stable keys are
`basic_info`, `weekly_summary`, `living_activity`, `indoor_environment`,
`device_status`, `risk_management`, and `guardian_actions`. The combined
`living_activity` object contains descriptions, one tag, `activity_detection`,
and `remote_control_usage`. Raw numeric values sit beside approved display strings
so a frontend does not need to parse Markdown, units, or percentages. The typed
object is returned in interactive graph results and included in each existing
report JSON artifact and `reports.jsonl` record. PostgreSQL persistence of this
template is intentionally not part of this change. ZIP download additionally
places the same object in `json/<ward_id>.json`; existing Markdown paths and
archive entries remain available.

The v3 display policy distinguishes missing temperature-only, humidity-only,
and combined indoor-environment data. Missing environment metrics display `-`;
missing count-based device metrics display `0`. Their JSON raw values remain
null, so the presentation fallback cannot be mistaken for a measured or
classified value.

The v4 presentation contract renames the indoor-environment and device-status
`summary` keys to `tag` and renders `태그` throughout the Markdown detail
sections. The deterministic stable-week guardian card now outputs template ID
`GUI_GOOD_01` when no CAUTION/RISK action card is selected. A truly empty
guardian-action result keeps its message and exposes the same code as
`template_id` in both JSON and Markdown.

The v5 device-detail contract renders `정보 수신` from the current
`covered_days` value and calculates `전원 확인` as the seven-day selected period
minus that value. These JSON metrics are named `normal_reception_days` and
`power_check_days` and render with day units. The prior source-derived power
pattern count remains available only to the existing status classifier.

An approved forward SQL migration defines
`ansimk.ward_weekly_report` for JSON report persistence. The table has
an identity primary key, a restricted foreign key to `ansimk.resources_ward`,
weekly start/end dates, optional score and status metadata, non-null JSONB
`report_data`, timestamps, and a unique ward/week-start constraint. Interactive
previews remain non-writing. After bulk JSONL and ZIP artifacts are generated,
the finalizer uses the dedicated `WEEKLY_REPORT_STORAGE_DATABASE_DSN` connection
to upsert frontend `template_data`. It sends bounded batches inside one
transaction, uses the inclusive Sunday report date as `week_end_date`, and
updates score, status, JSON, and `updated_at` on a ward/week conflict. A write
failure rolls the operation back and prevents the job from completing.

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

Open `/agents/1`, approve the live private-model run, and start with 100–1,000
reports before attempting 10,000. The UI polls
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
volume. Each process admits up to `WEEKLY_REPORT_ACTIVE_JOB_LIMIT` distinct jobs
(four by default), oldest first, so a second submitted job starts without
waiting for the first job to finish. All jobs in that process share the single
`WEEKLY_REPORT_WORKER_CONCURRENCY` item semaphore; four active jobs therefore do
not turn the default thirty-two report/model-call ceiling into one hundred
twenty-eight. Expired producer, item, and finalizer leases are reclaimed.
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

The configured worker concurrency (32 by default) is a process-wide
application-side upper bound across active jobs, not a guarantee of 32
simultaneous GPU sequences. The inference server still owns continuous batching
and admission. When bulk and Chat share one model endpoint, a load run can
increase Chat latency; production must reserve interactive inference capacity
or use a separate bulk endpoint. The UI requires explicit confirmation and
displays this limitation before submission.

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
  atomic private artifacts, manifest/JSONL/Markdown/per-ward JSON export, safe
  partial failure, cancellation, recent-job ordering, private control API validation,
  checksum-verified download, non-zero response length, and lease recovery. A PostgreSQL-backed
  integration run and a representative 10,000-report model benchmark remain
  deployment release gates.
- Deployment checks require Ruff, pytest, LangGraph validation, Compose config,
  and a live readiness check with operator-supplied secrets.


## Database recovery — 2026-09-08

Completed bulk artifacts can be recovered into the report table using the
[operator recovery command](weekly-report-database-recovery.md). It verifies
terminal job state, expected count, checksums, ward identity, and reporting week
before using the existing transactional upsert; it does not regenerate reports.

## Explicit insert timestamps (2026-09-08)

Production recovery identified `created_at` NOT NULL failures for all 6,437
reports. The writer now supplies `NOW()` for both `created_at` and `updated_at`
on INSERT, without depending on table defaults. Conflicting ward/week updates
preserve `created_at` and refresh `updated_at`. This applies to regular bulk
finalization and recovery, and requires rebuilding the worker image. No table
alteration or report regeneration is required. Retry recovery with `--write`
after rebuilding; `--skip-not-null` remains optional for other rejected rows.
