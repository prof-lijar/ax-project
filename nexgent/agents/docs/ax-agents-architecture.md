# AX Agents Architecture

Date: 2026-09-01

Status: **Authoritative implementation specification**

This document is the required starting point for any material change to AX
agent runtime, graph orchestration, tools, APIs, persistence, deployment,
security, or evaluation. `AGENTS.md` requires contributors and agents to read
it before implementation and update it when architecture changes.

## Implementation status

The baseline described here is implemented as of 2026-08-05:

- `uv` workspace with deployable `apps/`, self-contained `workflows/`, and
  shared `packages/` for contracts, runtime, tools, integrations, persistence,
  observability, and evaluations;
- versioned Pydantic contracts with strict unknown-field rejection;
- runtime context, execution limits, normalized errors, and LangGraph config
  helpers;
- deterministic compiled graph exported from `workflows/smoke` and configured in
  `langgraph.json`;
- capability/risk-based tool authorization policy;
- reusable authorized `web_search` and SSRF-safe `web_fetch` tools backed by a
  private no-provider-key SearXNG deployment;
- declarative remote MCP registry, environment-backed Streamable HTTP client,
  discovery CLI, and policy-enforced namespaced MCP tool adapters;
- Agent Server adapter port and FastAPI gateway with health, submit, status,
  SSE events, and interrupt-resume route contracts;
- self-hosted PostgreSQL/Redis/Agent Server Compose baseline;
- pooled asynchronous OpenAI-compatible model adapter and one-turn chat graph;
- dedicated one-turn `rag_chat` graph with read-only RAG Top-5 grounding,
  deterministic empty-context handling, and code-owned source provenance;
- transient document/image attachment references, secure local artifact reads,
  and opt-in multimodal chat content;
- architecture governance in `AGENTS.md` and this document.

Validation completed:

```text
ruff check apps workflows packages tests -> passed
python -m pytest -q                  -> 13 passed
langgraph validate                  -> valid, 1 graph found
docker compose config               -> valid with .env.example
langgraph dev + POST /runs/stream   -> streamed ack: hello
```

The real Agent Server adapter, authentication provider, durable production
database, and business-specific write tools remain intentionally unimplemented.
Compose image build, PostgreSQL/Redis integration tests, and a live model
readiness check are the next deployment verification gates.

## RAG Chat orchestration (2026-08-25)

The Chat page now has a real `RAG Agent` execution path through the dedicated
`POST /api/rag/chat/stream` backend endpoint. The backend reuses its existing
Agent Server SSE relay but selects only the registered `rag_chat` graph for
this route. Normal `/api/chat/stream`, preview agents, and Weekly Reporter
routing are unchanged.

`rag_chat` calls the existing read-only `GET /rag/v1/search` endpoint with the
exact current question and fixed `top_k=5`. It preserves returned order and
provenance, treats all retrieved text as untrusted evidence in one user
message, and keeps its grounding policy in a separate system message. Zero
results deterministically return an insufficient-context response and skip
model generation. With results, the graph reuses the same pooled
OpenAI-compatible `/v1/chat/completions` adapter, environment-driven model/base
URL/auth path, retry policy, streaming, and safe errors as normal Chat. It then
appends Markdown-escaped sources in code, including a null-provenance legacy
fallback.

The graph remains a one-turn, text-only Phase 1 workflow. Attachments are
disabled in the RAG Agent UI and rejected by the strict JSON API contract.
Production search remains vector-only; the lexical/RRF experiment was not
enabled and the RAG retrieval implementation, schema, chunking, embeddings,
OCR, and DOCX paths were not changed.

`RAG_SERVER_BASE_URL` configures the server-side read-only RAG origin and must
be reachable from the Agent Server runtime without embedded credentials. The
live Agent Server reaches the systemd-managed host RAG API through
`http://host.docker.internal:8765`; a narrowly scoped host network policy allows
TCP 8765 for that runtime. The host service is enabled through
`multi-user.target`; its PostgreSQL container lifecycle remains separate. The
registered `rag_chat` graph, deterministic
empty-corpus branch, populated retrieval/generation path, backend SSE relay,
and browser rendering were live-validated on 2026-08-25. The pre-empty
test-data backup was deliberately not restored; one synthetic Direct Text
source was added only for the populated-path validation. Phase 1 remains
one-turn and text-only, with no Chat attachment ingestion, conversation memory,
Nextcloud link, deduplication/versioning, or production Hybrid retrieval. See
[RAG Chat Agent](rag-chat-agent.md) for the endpoint, prompt, sources, evidence,
and deployment details.

## Weekly-report bulk execution (2026-08-20)

The manual `ansimk_weekly_reporter` LangGraph remains the compatibility path
for interactive batches of at most twenty-five reports. High-volume generation
is a separate workflow-owned execution path in `workflows/weekly_report/bulk`.
It does not create one graph branch or one agent per ward and does not place
thousands of reports in LangGraph state.

An operator submits an idempotent job for at most 10,000 reports. One leased
producer consumes the existing private source API in ordered pages of at most
one hundred and stages each validated metric snapshot exactly once. Bounded
asynchronous consumers claim independent wards from PostgreSQL with
`FOR UPDATE SKIP LOCKED`, call the existing reporter specialist, and atomically
write report artifacts. Producer, item, and finalizer leases can be reclaimed
after process loss. A worker process admits up to four distinct jobs by default,
oldest first. All active jobs share the same process-wide item-concurrency
ceiling, so admitting another job does not multiply simultaneous model calls.
Additional worker processes or containers add bounded consumer capacity while
the PostgreSQL leases prevent duplicate item completion.

The separate bulk-job PostgreSQL contains only job metadata, opaque cursors,
artifact references, checksums, attempt counts, leases, and safe error codes.
Input snapshots, rendered reports, and the ZIP export live on a private
persistent volume with owner-only permissions and atomic replacement. The
terminal ZIP contains
`manifest.json`, `reports.jsonl`, deterministic `reports/<ward_id>.md`
Markdown files, and frontend-ready `json/<ward_id>.json` template files.
Artifacts expire after seven days; long-term report history, a public bulk API,
schedule persistence and execution, and bulk Slack delivery are deliberately
out of scope. Slack remains a separate human-approved side-effect boundary.

The model path is LLM-first for every report. OpenAI-compatible servers receive
the dedicated weekly-summary system prompt plus validated report-facing data
and return one plain-text Korean paragraph; the existing single correction and
disclosed deterministic fallback policy is unchanged. Python owns all metrics,
section statuses, and rendering. Worker concurrency is async and
bounded—Python threads and process-local sub-agent fan-out are not the scaling
boundary.

Weekly Reporter structured-template update on 2026-09-02: every
`WardWeeklyReport` retains its `markdown` field and additionally returns
`template_data`, now versioned as `weekly-report-v5`. Stable keys cover basic
information, the LLM-authored summary, the combined living-activity section,
the remaining deterministic detail sections, and guardian actions. Raw numeric values and approved display
strings are both present, avoiding client-side parsing and duplicated product
logic. Interactive responses and existing report JSON/JSONL artifacts carry
the new field. The bulk finalizer also persists that frontend object to the
dedicated report table described below. ZIP downloads
also expose each `template_data` object as `json/<ward_id>.json` while keeping
all existing entries and Markdown paths intact.

Weekly Reporter activity-format update on 2026-09-02: the former sibling
`생활 활동` and `생활 패턴` sections are combined under one `생활 활동` parent.
Its children are `활동감지` and `리모컨 이용`; child descriptions and summaries
are removed. The parent renders the two available descriptions, collapses two
unavailable comparisons into one approved data-limitation sentence, and shows
one `태그` selected by `RISK`, `CAUTION`, unavailable, then `GOOD` severity.
Equal statuses prefer `활동감지`. Calculation bands and the LLM summary inputs
remain unchanged.

Weekly Reporter missing-metric display update on 2026-09-02: indoor-environment
rendering now distinguishes temperature-only, humidity-only, and combined data
limitations with approved Korean copy and displays unavailable metrics as `-`.
Count-based device metrics without source values display `0`. Structured raw
values remain null in both cases, and neither display fallback changes status
calculation or the LLM fact package.

Weekly Reporter tag-contract update on 2026-09-02: all deterministic detail
sections render the label `태그` rather than `요약`. The frontend template
renames indoor-environment and device-status `summary` keys to `tag`, requiring
the `weekly-report-v4` version. When no CAUTION/RISK guardian action is selected,
the stable GOOD card outputs `GUI_GOOD_01` as its template ID. Markdown remains
available alongside the structured JSON. If no card is selected, the empty
state exposes the same code through `template_id` in both JSON and Markdown.

Weekly Reporter device-day display update on 2026-09-02: `정보 수신` now uses
the current covered-day count, while `전원 확인` is the selected seven-day
period minus that count. The v5 frontend keys are `normal_reception_days` and
`power_check_days`. The source-derived power-pattern occurrence count remains
internal to the backward-compatible device status policy and is no longer
rendered as the power metric.

Weekly Reporter report-storage update on 2026-09-03: the workflow-owned
`ansimk.ward_weekly_report` table is the durable frontend JSON target. After
generating verified JSONL and ZIP artifacts, the bulk worker streams completed
report artifacts through a dedicated writer DSN into bounded 500-row upsert
batches inside one transaction. `report_data` contains `template_data` only;
score and status are copied to queryable columns, and `week_end_date` is the
inclusive Sunday shown to the guardian. The ward/week unique key makes a
reclaimed or repeated finalization idempotent. Any write or count mismatch
rolls back storage and fails the job. The private source service and interactive
preview remain non-writing, while bulk-job metadata storage stays separate.

Weekly Reporter storage-table rename on 2026-09-04: the approved durable target
is now `ansimk.resources_ward_weekly_report`, superseding the original table
name in the 2026-09-03 record above. The schema remains `ansimk`; the columns,
foreign key to `ansimk.resources_ward`, unique ward/week key, atomic upsert
behavior, and writer configuration are unchanged.

Weekly Reporter concurrent bulk-job update on 2026-09-04: the durable worker no
longer awaits one entire job before admitting the next. It runs up to
`WEEKLY_REPORT_ACTIVE_JOB_LIMIT` distinct jobs per process (default four),
selects unadmitted jobs oldest first, and isolates task failure and cancellation
by job. All admitted jobs share one `WEEKLY_REPORT_WORKER_CONCURRENCY` semaphore
per process. This keeps aggregate report/model work bounded at the existing
limit rather than multiplying it by the number of active jobs. Producer, item,
and finalizer leases retain restart and multi-process recovery behavior.

Weekly Reporter frontend simplification on 2026-09-04: `/agents/1` is now a
bulk-only operator surface. The Quick Preview mode, its per-report review UI,
the Chat-triggered Weekly Reporter run, and the frontend `/runs/stream` parser
and report contracts were removed. Weekly Reporter is no longer marked as
Chat-capable in the frontend catalog. The retired `/test-agent` path normalizes
to `/agents/1`, and its sidebar entry is gone. The durable bulk control client,
status polling, cancellation, recent jobs, and verified ZIP download remain.
The registered interactive graph remains a backend compatibility boundary; it
has no first-party frontend caller.

Weekly Reporter schedule UI prototype on 2026-09-04: the bulk-only
`/agents/1` page renders a schedule card directly below its heading. It
defaults to enabled, Monday at 03:00, repeats weekly, and displays
`Asia/Seoul` as the time zone. Weekday, time, and enabled state are local
React state only. The save action is disabled and the page explicitly states
that changes are not saved and no automatic job will run. This adds no timer,
API contract, durable schedule record, scheduler process, or job submission
path; manual durable bulk controls remain unchanged.

Release capacity is measured end to end against a representative private-model
deployment. The hard gate is 10,000 reports in at most two hours (at least
1.389 reports/second); the healthy target is ninety minutes (at least 1.852
reports/second). Operators increase worker concurrency only until model or
source saturation, then add private inference replicas. vLLM prefix caching,
continuous batching, and structured output may be enabled at the inference
deployment, but replica count is derived from the observed benchmark rather
than fixed in application code.

Bulk operator API and UI update on 2026-08-20: the existing durable worker is
now reachable from the Weekly Reporter page through a separate private
`apps/weekly_report_bulk_api` control process. Its strict endpoints submit an
idempotent job, list and inspect content-free progress, request cooperative
cancellation, and stream only checksum-verified terminal ZIPs. Recent-job
listing was added to the generic bulk store so browser refresh does not lose
operator visibility. The control API and worker share the job database and
private artifact volume but remain separate deployment and ownership
boundaries; the API never executes model calls.

The default development Compose topology starts the bulk PostgreSQL queue,
worker, and control API. The control API has no host port and is reachable in
the browser only through the existing Vite development proxy. The `/agents/1`
workbench exposes only durable bulk generation for up to 10,000 reports. It
does not call the interactive LangGraph reporter. The bulk view displays source
discovery in 100-item pages, active consumer count,
queued/completed/fallback/failed counts, observed throughput, projected finish,
recent jobs, cancellation, and ZIP download. Submission requires explicit
acknowledgement that allowlisted care-derived facts will reach the configured
private model and that a shared model endpoint may slow Chat.

This is an observable execution path, not evidence that the two-hour SLA has
been achieved. A real PostgreSQL-backed run and representative 10,000-report
private-model benchmark remain release gates. Production exposure also requires
an authenticated gateway; the Vite proxy is trusted-development plumbing only.

Bulk cancellation and paging update on 2026-08-24: durable bulk source pages
now contain at most one hundred wards, while the interactive compatibility
graph remains capped at twenty-five. A persisted cancellation request is
watched during execution; the worker cancels in-flight async model calls,
marks pending and leased items cancelled, and exports only reports that had
already completed. The operator UI sends the same cancellation request for
Cancel, stop-and-refresh, page refresh, navigation, and unmount. Browser
keepalive delivery is best-effort, while the explicit Cancel response remains
the confirmed control path.

Weekly Reporter bulk recovery update on 2026-08-26: production-like history
showed normal forty-report jobs completing in roughly 27–47 seconds, but one
oldest active job remained non-terminal for about 31 minutes and queued later
jobs behind it. The runner now converts producer, consumer, and finalizer
exceptions into persisted terminal job failures, cancels unfinished items,
and lets the durable worker continue polling. Each narrative generation has a
configurable 60-second default deadline and degrades to the deterministic
grounded fallback on timeout. Verified ZIP responses are sent in bounded
chunks with the verified artifact byte size advertised as `Content-Length`.
Regression tests cover producer failure, an indefinitely slow model item, and
the non-zero ZIP response length so these failure modes cannot silently return.

Architecture update on 2026-08-05: workflow modules moved from `graphs/` to
`workflows/`; `apps/workers`, `packages/persistence`, and
`packages/observability` were added as explicit scaling boundaries; shared
tests were grouped by intent. Ruff, 13 tests, direct smoke execution, and
`langgraph validate` passed after the move.

Architecture update on 2026-08-10: `ax-integrations` gained a provider-neutral
chat-model port and a concrete OpenAI-compatible streaming adapter. The new
`workflows/chat` graph provides a minimal async LLM path while `workflows/smoke`
remains deterministic. Model settings are loaded only in the integration layer,
connections are pooled, retries are bounded, and credentials stay outside
graph state. Ruff, 24 tests, and `langgraph validate` with two registered graphs
passed for this change; the live private endpoint check remains deployment-owned.

Runtime compatibility update on 2026-08-10: LangGraph API 0.12.0 loads graph
entries configured as Python file paths without package context. Graph
entrypoints therefore use absolute workflow imports, while package-internal
modules may continue using relative imports. A contract test now loads every
`langgraph.json` entry using the runtime's file-versus-module behavior so
validation cannot pass while development startup fails.

Development network update on 2026-08-10: the documented local Agent Server
command binds specifically to `192.168.0.18:2024` so trusted LAN peers can use
it. This is an in-memory, noop-auth development listener only. Port 2024 must
remain restricted to the trusted network; production traffic still terminates
at the authenticated gateway, with Agent Server kept private.

Containerized development update on 2026-08-10: the root `compose.yaml` builds
a license-free development image that runs `langgraph dev` automatically. The
process binds `0.0.0.0:2024` inside its container and Docker publishes it only
as `192.168.0.18:2024`; model settings are injected from the ignored root
`.env`. This in-memory, noop-auth path is separate from the licensed standalone
deployment baseline under `infra/compose` and is restricted to trusted-LAN
development.

Parent stack update on 2026-08-10: `/nexgent/compose.yaml` now composes this
development Agent Server with the existing backend and frontend. Its build
context remains `/nexgent/agents`, the frontend proxy resolves the container as
`http://agent-server:2024`, and the published listener remains
`192.168.0.18:2024`. Running `docker compose up --build` from `/nexgent` starts
all three development services.

Root production-server update on 2026-09-03: `/nexgent/compose.prod.yaml` adds
an isolated `nexgent-prod` Compose project for the separate stable server used
by the designated user group after application testing. It has separate host
ports and volumes, an immutable backend container, and a compiled frontend
served through Nginx. In this operational naming, `production` distinguishes
the stable user server from the new-feature development server; it does not
mean a LangSmith-hosted deployment. The stable server intentionally reuses the
current environment values and tested in-memory Agent Server implementation
for now. References to a `production-grade Agent Server` elsewhere in this
document describe a separate future hardening milestone and are outside the
current two-server separation scope.

Chat streaming update on 2026-08-10: the chat workflow now consumes the
provider adapter's asynchronous token iterator directly and emits only text
deltas through LangGraph's `custom` stream mode. It still returns the assembled
response in graph state, so clients request both `custom` and `values`: custom
events provide immediate display updates and the final values event verifies
the completed response. Provider URLs, credentials, and raw provider events
remain inside the integration boundary and are never included in graph stream
payloads. Full Ruff validation and all 26 agent tests passed after this change.
The chat workflow's bounded output budget is 2,048 tokens, increased from the
initial 500-token prototype limit to support detailed operational answers.

Chat cancellation update on 2026-08-10: the stateless frontend run request now
sets Agent Server's `on_disconnect` policy to `cancel`. Aborting the response
stream therefore cancels graph execution and propagates async cancellation to
the OpenAI-compatible provider stream, rather than leaving model generation
running after the UI stops. This uses Agent Server's run lifecycle contract and
does not add provider-specific cancellation logic or durable chat threads.

Web research tools update on 2026-08-12: `ax-contracts` now defines strict,
versioned search, source, and fetched-page schemas. `ax-tools` exposes
workflow-neutral `web_search` and `web_fetch` factories with injected executors,
read-risk authorization, deterministic idempotency keys, structured artifacts,
and safe retry-classified failures. `ax-integrations` provides pooled SearXNG
search and public-page fetch adapters; page retrieval pins validated DNS
addresses, rejects non-public destinations and unsafe redirects, bounds
content, and extracts readable text with Trafilatura. SearXNG is digest-pinned
and private in every Compose topology. The current chat graph is unchanged.
Ruff, 52 deterministic tests, two LangGraph entrypoints, the smoke graph, and
all three Compose configurations passed. The opt-in live quality evaluation was
skipped as designed; live container startup still requires operator Docker
access on the host.

Weekly reporter update on 2026-08-12: `ansimk_weekly_reporter` is the first
business-specific graph. A manually triggered coordinator loads a stable
three-user mock work-activity window and uses bounded LangGraph fan-out into an
isolated per-user calculation, Korean narrative, and Markdown composition
subgraph. Python owns every numeric calculation; the OpenAI-compatible model
may produce only validated, grounded prose. The initial narrative contract was
digit-free; the later structured-summary policy allowlists only meaningful
verified values. Model configuration, request,
empty-output, and narrative-validation failures yield disclosed deterministic
fallback reports without failing the batch. Strict weekly-report contracts and
deterministic evaluator gates cover ordering, Korean structure,
personalization, numeric grounding, and fallback disclosure. The workflow is
registered in `langgraph.json`; scheduling, real database access, report
persistence, authentication, and delivery remain deferred integration work.
Ruff, all 70 deterministic tests, and LangGraph validation with three graph
entries passed; the opt-in live web-quality evaluation remained skipped as
designed.

MCP integration update on 2026-08-13: `ax-integrations` now uses the official
MCP Python SDK behind a strict JSON server registry. HTTP headers resolve only
from environment variables, clients reuse bounded connection pools, failures
are normalized without credentials, and `ax-mcp inspect` performs non-secret
server/tool discovery. `ax-tools` converts discovered definitions into
namespaced LangChain tools, validates remote JSON Schemas locally, rejects
unclassified risks, and applies the existing per-call authorization policy.
The first configured endpoint, `db_mcp_server`, negotiated protocol
`2025-11-25` with server version `1.29.0`; its ten advertised read-only tools
are classified as `read` but are not automatically granted to any workflow.
Ruff, 84 tests with one opt-in live evaluation skipped, LangGraph validation
with three graph entries, both in-scope Compose configurations, live discovery,
and one allowlisted `server_info` call passed.

Weekly reporter MCP update on 2026-08-13: the production
`ansimk_weekly_reporter` repository now loads its fourteen-day activity window
through `db_mcp_server`. Its workflow-local gateway exposes only the classified
read tools `find_columns` and `query_data`; it never grants the remaining MCP
surface. A strict canonical row contract covers user identity, activity date,
task counts, focus minutes, and blocker counts. Operators may configure an
explicit schema, table, and canonical-to-physical column mapping; otherwise,
exact-name discovery must identify one common table or view. Retrieval selects
only required columns, uses half-open date filters and deterministic sorting,
pages by one hundred rows, caps the batch at fourteen hundred rows, validates
all untrusted output, and fails closed without a production mock fallback. The
stable mock repository is test-only. The MCP protocol and tool schemas were
verified live, while end-to-end data readiness remains blocked by the remote
server's rejected backing PostgreSQL credential. Ruff passed, 89 tests passed
with one opt-in live evaluation skipped, all three LangGraph entries validated,
and both Compose configurations rendered successfully.

Ward-risk prototype update on 2026-08-14: live schema inspection showed that
the Ansimk database does not contain the generic task/focus/blocker contract and
that `analysis_wardperiodreport` is currently empty. The weekly graph now uses
the populated `ansimk.analysis_warddangerdaily` source for a deliberately small
end-to-end validation slice. Its repository grants only `query_data`, scans one
bounded identity page for the requested fourteen-day window, selects three
sorted wards by default, and re-queries those identities for complete daily
histories. Python computes current and previous danger-day counts and their
delta; an isolated branch generates validated Korean narrative and grounded
Markdown for each ward. Output warns when source selection is truncated, all
MCP data remains untrusted until validated, and no write occurs. A live cycle
for 2026-08-03 completed through MCP, the OpenAI-compatible model, LangGraph,
and terminal rendering with three AI-narrated reports. This is a validation
prototype, not an approved production interpretation of risk data. Ruff
passed, 86 tests passed with one opt-in live evaluation skipped, all three
LangGraph entries validated, and both Compose configurations rendered.

Weekly reporter production-path update on 2026-08-18: the danger-day MCP
prototype was replaced by a private `apps/weekly_report_api` FastAPI process.
A reusable `asyncpg` integration owns pooled read-only PostgreSQL transactions;
workflow-owned parameterized queries calculate current and prior raw seven-day
environment, activity, sleep, risk, danger-day, and dispatch metadata. The
graph consumes versioned snapshots through a private-network workflow-local
HTTP client and preserves the registered graph ID plus compatibility
`danger_days` fields. Python converts verified metrics into qualitative facts
before a workflow-local reporter specialist writes warm Korean prose. The
model sees no raw rows, free-text notes, or numeric values; structured output
receives one validation retry and then a disclosed deterministic fallback.
Automatic ward discovery is ordered, cursor-paged, and capped at twenty-five;
explicit IDs return missing wards as skipped. Scheduling, delivery, and report
persistence remain deferred.

Outbound Slack integration update on 2026-08-18: `ax-integrations` now owns a
reusable async adapter over the official Slack SDK and `chat.postMessage`.
Environment configuration defines the default channel and an allowlist of
logical destinations; runtime or model-generated channel IDs cannot expand
that allowlist. The adapter supports text, Block Kit, and thread replies with
bounded timeouts, one `Retry-After` rate-limit retry, sanitized result objects,
and content-free structured delivery logs. The weekly reporter adds an
explicit post-generation sender for an approved configured destination. It is
kept outside graph execution and requires human confirmation before sending
care-related content, preventing graph retries from duplicating Slack side
effects. No inbound Slack capability was introduced.

Weekly reporter source-schema correction on 2026-08-19: live execution against
the configured archive database showed that unqualified relation names resolve
through a deployment-specific `search_path`, while matching tables exist in
`ansimk`, `ansimk_clone`, and `archive`. All weekly-report SQL now explicitly
qualifies the approved `ansimk` schema. Clone and archive relations cannot be
selected implicitly, and a regression test enforces that source binding.

Weekly Reporter frontend integration update on 2026-08-19 (superseded on
2026-09-04): at that time, the catalog route `/agents/1` owned the interactive
workbench, while `/test-agent` remained an alias for isolated testing. An
operator-triggered request sent an explicit limit of
1–25 selected in the UI through the existing Agent Server SSE boundary; the
default is three, and no query or model call occurs merely by opening the page.
The Agent Server run configuration caps graph concurrency at four so a larger
batch does not fan out without a bound. The frontend validates the expanded weekly
metric, narrative, generation, skip, and cursor contract, selects the first
ordered report by default, and renders only useful indicators plus safe
Markdown rather than exposing raw report JSON. The root development Compose
stack now includes the private weekly-report FastAPI service and gates Agent
Server startup on its database-backed readiness endpoint.
The read-only source path was verified with an actual three-item batch. A live
model-backed batch remains an explicit approval gate because even the
allowlisted qualitative fact package is ward-derived care information.

Weekly Reporter progress correction on 2026-08-19: the frontend Agent Server
request enables subgraph streaming because `ward_report_ready` is emitted from
each isolated per-ward branch. The SSE client accepts namespaced `custom|...`
events as validated progress while continuing to accept the terminal report
only from the top-level `values` event. This prevents completed batches from
displaying a stale zero-of-requested report count without weakening result parsing.

Weekly Reporter environment-policy update on 2026-08-26, superseded by the
2026-08-27 spreadsheet-template policy below: a product-approved,
deterministic presentation rule classifies daily indoor maxima using inclusive
year-round recommended ranges: `15℃ ≤ temperature ≤ 31℃` and
`30% ≤ humidity ≤ 70%`. Python converts below/above-bound measurements into
cold/hot or dry/humid qualitative facts.
The reporter receives only qualitative evidence, and validation enforces every
material environment issue without exposing numeric thresholds to the model.

Weekly Reporter grounded-summary correction on 2026-08-25: `한주 총평` now
scales from one to six sentences according to the available qualitative facts,
with no minimum character count. Available observations take precedence over
coverage metadata. Prompt validation rejects missing-data apologies,
unsupported health reassurance, future-report promises, and guardian
pleasantries, while the deterministic fallback concatenates only verified
facts and may return a single short observation.

Weekly Reporter insight-summary refinement on 2026-08-25: the versioned prompt
now asks for a formal, guardian-facing weekly insight rather than a flat fact
list. Normal device reception may establish observation reliability, related
movement and remote-control facts are synthesized into the overall activity
flow, and material exceptions follow with a natural contrast. Headline and
analysis validation requires warm `합니다체`; the deterministic fallback mirrors
the same ordering, synthesis, and formal register without adding unverified
interpretation.

Weekly Reporter evaluatable-area summary policy on 2026-08-25: workflow-owned Python
now derives `valid_days` from current covered dates and derives data quality
from valid-day coverage plus approved device power/position status. It selects
`ALL_GOOD`, `MIXED`, `RISK`, `LOW_DATA`, or `PARTIAL_DEVICE` before the model
call and produces a semantic INTRO/LIFE/ENV/SAFE/CLOSE outline. All evaluatable
activity, environment, and device items are provided as evidence; the later
valuable-insight policy makes only material issue topics mandatory and allows
low-value GOOD facts to be omitted. Unavailable items are omitted entirely
rather than rendered as insufficient-data or cannot-compare filler. The LLM may
only synthesize the supplied grounded evidence; the renderer owns the integrated
CLOSE action.
Narrative validation admits only significant numeric tokens already present in
the outline and rejects invented counts. This policy supersedes the earlier sparse single-observation layout for
production fact packages; direct compatibility packages without an outline
retain the shorter fallback behavior.

Weekly Reporter topic-removal update on 2026-08-25: sleep and dispatch are no
longer report topics. They are excluded from the semantic outline, model fact
package, generated headline and analysis, observations, suggestions, and all
rendered Markdown sections. The summary now covers only evaluatable activity,
indoor environment, and device reception. The detail sections retain
risk-event detection/resolution under risk management
without rendering dispatch data. Private source-contract compatibility fields
remain temporarily available upstream but cannot cross the reporting boundary.
When all three report topics are unavailable, an empty available-item list is
preserved as empty rather than expanded to default topics. The narrative uses
the grounded coverage headline with empty analysis and observations, and the
renderer completes the report without indexing nonexistent evidence. This
zero-block path is an explicit terminal fallback state rather than a failed
Agent Server stream.

Weekly Reporter environment RISK correction on 2026-08-25: directional RISK
classification now uses daily maximum extrema and requires the same extreme on
four or more dates. The strict thresholds are maximum humidity below 30% or
above 70%, and maximum temperature below 15℃ or above 31℃. Exact boundary
values do not count as extreme days. Recommended-range temperature and humidity
departures still drive GOOD and CAUTION, while combined departure on four or
more dates selects RISK 5. Python owns all daily aggregation, boundary checks,
counts, precedence, and rendered status; the model receives qualitative copy
only.

Weekly Reporter valuable-insight summary update on 2026-08-26: the model no
longer follows a fixed LIFE/ENV/SAFE order or emits one sentence for every
available report area. Python still supplies the complete allowlisted
qualitative evidence and owns all calculations, statuses, issue detection, and
suggested actions. The narrative must cover every material CAUTION or RISK
topic, but may omit low-value GOOD facts and combine related evidence into one
to four connected weekly insights. Unavailable items remain fully excluded;
sleep and dispatch remain excluded from the entire report. Validation retains
topic allowlisting, material-issue coverage, numeric grounding, formal Korean,
safety filters, and the terminal zero-evaluable-item path.

Weekly Reporter spreadsheet-template policy update on 2026-08-27: the product
owner promoted spreadsheet `1tOuquKA_QrsWfWI6JlVTQ2z_pS2C5O9j5r8u6ZEo6QM`,
sheet `1395281680`, as the versioned classification, copy, and guardian-guide
policy. Prompt version `weekly-korean-sheet-template-v16` follows the approved
all-GOOD sequence: activity, indoor environment, and device reception, joined
by `구체적으로`, `이와 함께`, and `또한`. A byte-for-byte golden test locks the
full Markdown example, while deterministic Python continues to own arithmetic,
statuses, copy selection, guide priority, and rendering. The promoted rules
also make 150% activity `CAUTION`, include exact environment range boundaries,
use daily maxima for environment classification, and prioritize device issues
before activity, environment, and the general check-in.

Weekly Reporter risk-score presentation update on 2026-08-25: the deterministic
renderer now exposes the already-calculated current-week average `risk_score`.
Python rounds the average to a whole point using half-up rounding and classifies
it with the product-approved statuses `76–100 GOOD`, `26–75 CAUTION`, and
`0–25 RISK`. The report shows the grounded score, uppercase status, and exact
Korean guidance; missing or invalid source scores remain explicitly
unavailable. The score and classification stay outside model-authored prose.

Weekly Reporter activity presentation update on 2026-08-25: the source
contract now carries weekly totals calculated directly from non-null
`movement_count` and `remote_control_count` rows. Workflow-owned Python compares
each current total with its previous-week total, assigns the product-approved
`GOOD`, `CAUTION`, or `RISK` status, and renders the exact Korean guidance and
short summary. Missing totals and zero previous totals fail closed as an
unavailable comparison. Only the qualitative guidance may enter the reporter
prompt; totals, percentages, and thresholds remain deterministic report data.

Weekly Reporter activity layout update on 2026-08-31: the shared numbered
`활동량` wrapper was removed. Movement now renders as the sibling `생활 활동`
section and remote-control use as `생활 패턴`; each owns a flat `지표` list for
the current total, comparison total, and percentage. Calculation and copy
selection remain deterministic and unchanged.

Weekly Reporter risk-management layout update on 2026-08-31: the renderer no
longer emits the empty `위험 관리 기록` subsection or its unavailable-detail
placeholder. The section retains only the verified risk detection and normal
resolution counts; no source or calculation contract changed.

Weekly Reporter section-heading update on 2026-08-31: all main headings below
`주요 내용` are unnumbered. This applies to `생활 활동`, `생활 패턴`,
`실내 환경`, `기기 데이터 수신`, and `위험 관리`; guardian action-card list
numbering remains separate and unchanged.

Weekly Reporter living-activity copy update on 2026-08-31: the existing
movement ratio bands remain unchanged, while deterministic description and
summary copy now uses the approved `평소 수준`, `조금 감소`, `조금 증가`,
`많이 감소`, and `많이 증가` language.

Weekly Reporter living-pattern copy update on 2026-08-31: the same existing
ratio bands now map remote-control use to approved `TV 이용 등 일상적인 생활
패턴` descriptions and the summaries `평소 수준`, `조금 감소`, `조금 증가`,
`많이 감소`, and `많이 증가`. The living-activity copy is unchanged.

Weekly Reporter combined activity-summary update on 2026-08-31: Python now
maps the nine approved movement-plus-remote combinations to exact warm Korean
copy for the opening activity block in `한주 총평`. Prompt version
`weekly-korean-sheet-template-v16` requires the model to place that block first
after one connector without paraphrasing; validation enforces the same
contract and permits 해요체 only inside this Python-owned block. The block may
contain two sentences. Relevant indoor-environment and device findings remain
connected afterward, and the renderer still owns the separate closing action,
so the summary is not collapsed into a single activity sentence.

Weekly Reporter indoor-environment copy and boundary update on 2026-08-31:
all seventeen GOOD, CAUTION, and RISK variants now render the revised exact
guardian-facing description and short summary. Combined classification matches
the stated directional counters directly instead of inferring a direction
from aggregate departure days. The private source snapshot adds optional daily
maximum counters for temperature below 18℃ and humidity at or above 70%, used
only by cool-humid CAUTION and cold-humid RISK respectively. Older snapshots
without those fields fall back to the ordinary below-15℃ and above-70%
directional counters; raw source calculation and current fixtures provide the
new counters explicitly.

Weekly Reporter device-status copy update on 2026-08-31: the rendered
`기기 데이터 수신` heading is now `기기 상태`. Existing deterministic row
classification remains good, power, then position, with power-first weekly
precedence and two-occurrence CAUTION thresholds. GOOD, power-check, and
position-check results now render the newly approved exact descriptions and
summaries. Prompt version `weekly-korean-sheet-template-v17` uses `기기 상태`
as the model-visible topic label so generated summaries do not reintroduce the
retired section name.

Weekly Reporter guardian-action metadata update on 2026-08-31: deterministic
guardian guides now own an approved description, tag, and optional template
ID in addition to condition, status, and title. The increase actions apply to
movement and remote-control `CAUTION`; increase `RISK` no longer reuses them.
Rendered action cards contain only deterministic guides because model-authored
suggestions cannot supply an approved tag or template ID. Device issues remain
first, output remains capped at three cards, and the stable GOOD card requires
a GOOD weekly risk score with no CAUTION/RISK area state or detected risk
event. Prompt version `weekly-korean-sheet-template-v18` carries the expanded
candidate metadata but leaves selection and rendering in Python.

Weekly Reporter human-summary refinement on 2026-08-31: prompt version
`weekly-korean-sheet-template-v19` treats `한주 총평` as the primary guardian
customer explanation. The exact Python-selected movement-plus-TV block remains
first and byte-for-byte unchanged. When indoor-environment or device evidence
is available, validation now requires at least one supporting insight after
that block. The model prioritizes material changes, cross-area relationships,
observation reliability, and useful stable context, may combine related facts,
and is explicitly prevented from using numbered recitals or process-oriented
report filler. The deterministic fallback follows the same multi-insight rule.

Weekly Reporter natural-support summary update on 2026-08-31: prompt version
`weekly-korean-sheet-template-v20` adopts warm 해요체 for the entire structured
headline and analysis and rejects stiff administrative 합니다체. The exact
Python-owned activity block now begins the analysis directly without a forced
connector; the opposing CAUTION decrease/increase pair uses the approved
`활동은 조금 줄어든 모습이었지만...` wording. For valid data, the
personalized opening follows the deterministic weekly risk-score status, with
GOOD rendered as `전반적으로 평소와 비슷한 생활 흐름을 이어가셨어요`.
Normal device reception may establish observation reliability before a
material environment finding and its practical check. The renderer no longer
adds a separate generic CLOSE paragraph because guidance now stays beside the
finding that supports it. Deterministic fallback and validation mirror this
same structure without changing numeric calculations or status rules.

Weekly Reporter free-summary composition update on 2026-08-31: prompt version
`weekly-korean-free-summary-v21` replaces the normal-path Python summary mode,
headline, and exact activity-combination block with one LLM-authored paragraph.
The model receives only subscriber identity and deterministic report-facing
results for overall state, living activity, living pattern, indoor environment,
device status, risk management, and approved actions. It receives no raw rows,
totals, ratios, thresholds, dates, measurements, sleep/dispatch fields,
`summary_outline`, or prewritten summary sentence. The plain-text response must
be one body-only paragraph in warm 해요체 and is rejected if it contains digits,
`움직임`, `리모컨`, English status values, Markdown, formal administrative
endings, excluded topics, unsupported claims, or an omitted material issue.
Python splits the validated first sentence only to satisfy the existing
`WeeklyNarrative` contract, then the renderer rejoins it unchanged. Detail
sections and guardian actions remain deterministic; one correction and the
disclosed validated fallback remain reliability boundaries.

Weekly Reporter summary-quality guardrail update on 2026-09-01: prompt version
`weekly-korean-free-summary-v22` incorporates production feedback for sparse
and attention-heavy reports without changing deterministic calculations or
section classifications. The model synthesizes related findings rather than
copying section descriptions, states each fact once, and consolidates
same-purpose actions. Overall score-band and device-reception results cannot be
expanded into subscriber safety claims. An absent risk-detection record is
normally omitted and never means a dangerous situation did not occur; a
present record is mandatory but may be described only as a record, without
cause or severity inference. Material changes, device checks, and present risk
records prohibit a contradictory generic stable close. Validation rejects
repeated sentences or check-in intent, unsupported safety reassurance, omitted
present risk records, and stable closes that conflict with attention signals;
the single corrective retry receives a specific safe instruction. The
deterministic fallback strips section-local action repetition, combines the two
living-pattern trends, and appends at most one grounded action before passing
the same validator.

Weekly Reporter calm-record wording update on 2026-09-01: prompt version
`weekly-korean-free-summary-v23` keeps all deterministic record calculations,
detail-section labels, and classifications unchanged while removing categorical
or alarm-amplifying language from `한주 총평`. An absent separate record is no
longer included in the model payload; a present record is exposed only through
neutral `별도 확인 기록` data and summarized with calm observation wording.
Summary validation rejects `위험`, rushed or alarming words, and exclamation
marks, while still requiring a neutral mention when a record exists. Correction
feedback and deterministic fallback use the same unhurried language.

Weekly Reporter sparse-reception personalization update on 2026-09-01: prompt
version `weekly-korean-free-summary-v24` requires a usable supplied subscriber
name in the summary opening and rejects generic substitute honorifics in later
direct references. For deterministic complete lifestyle-information reception
absence (`기기 상태: 자료 없음`), the model payload is reduced to the subscriber,
one neutral reception-absence fact, and the approved power check. The summary
contains only the two grounded sentences `생활 정보가 들어오지 않은 날이
있었어요` and `기기 전원이 잘 연결되어 있는지 확인해 주세요`; unrelated
overall, activity, environment, and record interpretation are omitted.
Correction feedback and deterministic fallback enforce the same boundary.

Weekly Reporter guardian-persona and closing-order update on 2026-09-01:
prompt version `weekly-korean-free-summary-v25` removes risk-management and
separate-record data from the `한주 총평` model payload and forbids mentioning
or implying those records in the generated paragraph. This does not change the
deterministic `위험 관리` detail section. The summary persona is an experienced
customer-support adviser describing a parent who lives alone to an adult child
who lives apart. Activity evidence uses `활동` and `TV 이용 등 일상적인 생활
패턴`, never the unsupported duration phrase `TV 이용 시간`. All observations
must precede one consolidated final action sentence; validation rejects action
requests before the last sentence, new facts after an action, repeated actions,
and emotional-attitude directions such as `다정하게` or `따뜻하게`. Correction
feedback, the deterministic fallback, tests, and project-local skill references
share this boundary.

Weekly Reporter natural-flow and basic-information boundary update on
2026-09-01: prompt version `weekly-korean-free-summary-v26` removes overall
score-band and every other `기본 정보` value from the `한주 총평` payload. The
subscriber display name remains only as the identity required by the fixed
`지난 한 주 [이름]님은` opening. That first sentence now carries the core
activity and everyday lifestyle-pattern flow instead of repeating generic
overall copy. Normal summaries contain two to four sentences, join related
findings with natural Korean connective endings, and combine stable
activity/pattern and device/environment observations instead of reciting one
short sentence per section. A summary-only underscore immediately after a
bracketed service label is normalized to a space; stored identity and the
deterministic basic-information section remain unchanged. Risk-management
exclusion, non-duration TV wording, final-action ordering, correction, and
fallback boundaries from v25 remain in force.

Weekly Reporter opening-particle update on 2026-09-01: prompt version
`weekly-korean-free-summary-v27` prevents the fixed `지난 한 주 [이름]님은`
opening from immediately repeating the Korean topic particle with `활동은`,
`생활 활동은`, or `생활 패턴은`. The first clause uses an `이/가` subject form
such as `활동이` or restructures the phrase, while later contrastive `은/는`
remains valid. Deterministic validation triggers one specific corrective retry,
and the fallback applies the same grammar normalization. No calculation,
payload, rendering, or report-section boundary changes.

Weekly Reporter guardian-card title and environment-eligibility update on
2026-09-01: deterministic guardian cards now use observation-style titles for
stable, activity, everyday-pattern, environment, and device states while
preserving the approved descriptions, tags, and template IDs. Directional
environment variants one through four select `ENV_CAUTION_01` through
`ENV_CAUTION_04` for either CAUTION or RISK; combined variants five through
eight remain RISK-only. Prompt version `weekly-korean-free-summary-v28` labels
these values as guardian-card titles rather than closing action sentences.
Summary closing checks and deterministic fallback actions are grounded in the
verified section descriptions. Card priority, the three-card cap, stable-card
eligibility, and the zero-source device safeguard are unchanged.

Weekly Reporter environment day-count update on 2026-08-25, superseded by the
2026-08-27 spreadsheet-template policy above: the source service collapses
device summaries by date and deterministically counts departures from the
approved year-round temperature and humidity ranges using each date's maximum
values. The validated snapshot carries observed,
temperature, humidity, combined, and directional day counts. Workflow policy
assigns the approved uppercase status, exact Korean description, and short
summary with explicit precedence. The unspecified `반복` boundary is normalized
to four days, matching the explicit combined RISK duration; duplicated GOOD
copy maps to zero-day and one-day variants. The model receives only the chosen
qualitative description, while Python owns counts, status, ranges, and output.

Weekly Reporter device-reception update on 2026-08-27: the source service now
classifies each raw device-daily-summary row into validated good, power, and
weak-position occurrence counts. GOOD requires non-null/non-zero temperature,
humidity, light, and movement counts but ignores remote-control usage. Power
requires null temperature, humidity, and light counts regardless of activity
values. Position continues to inspect all five count fields after good and
power are excluded. Row classification is mutually exclusive in good, power,
then position order; workflow policy uses the approved two-occurrence threshold and
power-first weekly precedence to select `CAUTION`, then selects `GOOD` when at
least one good occurrence remains. Good occurrences do not need to equal every
source row. Unmatched rows are shown as a neutral `기타 수신 패턴` count and do
not override a matched weekly status. Received rows matching no weekly rule are
`판정 불가` and never create a false missing-data or power-check claim. Python
owns all raw comparisons, counts, precedence, status, and rendering; only
qualitative section assessments may reach the model.

Weekly Reporter zero-reception guidance update on 2026-08-26: a current period
with no device-daily-summary rows remains internally unavailable and does not
create a synthetic power occurrence, but its deterministic device-section
description asks the guardian to verify that device power is connected. Since
the status remains unavailable, the absence stays out of model-authored
insights and is not interpreted as a health or safety event.

Weekly Reporter guardian-guide update on 2026-08-26, superseded by the
2026-08-27 spreadsheet-template policy above: workflow-owned Python maps
validated activity changes, promoted environment conditions, and device
CAUTION results to a
product-approved internal condition, displayed title, and analysis sentence.
The renderer hides the internal condition and displays the title plus analysis,
orders device problems, activity changes, environment, then the general
check-in, caps output at three,
places deterministic guides before model suggestions, and closes `한주 총평`
with the first deterministic title. Hot and cold environment guides map by
semantic condition rather than internal variant number. The model may receive
approved titles as qualitative suggestions and fill remaining slots, but it
does not select, reorder, or rewrite deterministic guide content.

Weekly Reporter personalization and sensor-evidence update on 2026-08-26: the
Python-owned summary outline now creates the personalized first sentence from
the validated ward display name, and the renderer uses that headline directly.
The model prompt identifies the 안심지키미 expert-report role and receives
qualitative assessments for movement, remote control, temperature, humidity,
and device reception together with exact deterministic guardian candidates;
raw sensor rows, totals, and thresholds remain outside model state. Device-row
reception classification is mutually exclusive in good, power, then position
order, while weekly power and position CAUTION still require two occurrences.

Weekly Reporter template refinement on 2026-08-24: the weekly narrative heading
is now `한주 총평`, and its closing sentence repeats the first validated,
highest-priority guardian suggestion to keep the assessment warm and actionable.
The separate detailed action section remains. The score-band legend is no longer
rendered. The later topic-removal policy supersedes the original conditional
sleep-section behavior and excludes sleep from every report.

Frontend launch integration update on 2026-08-14 (superseded on 2026-09-04):
the Agents catalog marked `ansimk_weekly_reporter` as the single live-data
entry. Both of its **Run in Chat** actions created a one-shot run intent in UI
state and navigated to Chat. Chat consumed that intent once and chose the most
recent completed Monday in
the local calendar with `Asia/Seoul`, and calls the existing Agent Server SSE
boundary with cancellation enabled. Custom workflow events drive a live
four-stage trace; the completed per-ward Markdown reports and any warnings are
rendered in the transcript. Frontend parsing mirrors the ward danger-day
contract and rejects malformed events or results. The browser stores no MCP
endpoint or credential. Other preview agents still have no live runner.

Concurrent Chat/Weekly Reporter update on 2026-08-20 (superseded on
2026-09-04): the shared Chat workspace owned independent `chat` and
`weekly-report` request lanes. Each lane permitted one request, owned its own
abort controller and UI state, and could be cancelled
without affecting the other. Weekly Reporter remains visible as background
work while the normal Chat composer stays available. This removes a frontend
serialization bottleneck; the two requests may still compete for a shared
inference endpoint, so deployment capacity and latency remain separate release
concerns.

Agent Server concurrency correction on 2026-08-20: the development image starts
`langgraph dev` with `--n-jobs-per-worker 4`. The installed in-memory runtime's
implicit single-job default serialized otherwise-independent graph runs, so a
Chat run could not begin until the interactive Weekly Reporter run ended.
Operator-facing Weekly Reporter callers now use graph `max_concurrency: 1` to
avoid placing a four-report fan-out ahead of Chat at the shared model endpoint.
The four Agent Server slots are run admission capacity, not four guaranteed LLM
slots. Bulk workers remain a separate process boundary and require dedicated or
explicitly reserved inference capacity before production activation.

Repository validation for this correction passed the complete agent test suite
(one environment-dependent skip), full Ruff checks, three-graph LangGraph
validation, 97 frontend tests, the frontend production build, Tauri `cargo
check`, npm audit with zero vulnerabilities, and root Compose configuration.
The running stack was not replaced because the current account cannot access
the host Docker socket; deployment and the live overlapping-run browser check
remain explicit operator gates.

Weekly Reporter detail integration update on 2026-08-14 (superseded on
2026-09-04): the stable catalog route `/agents/1` rendered the live
`ansimk_weekly_reporter` workbench directly. Operators could select a reporting
Monday and timezone, observe
validated custom progress events, cancel the active Agent Server run, and
inspect per-ward Markdown and metrics without leaving the agent detail route.
The former `/test-agent` route reused the same workbench in test-oriented
presentation, while all other agent detail routes retained their preview UI.

Chat attachment runtime update on 2026-08-14: `ax-contracts` defines strict
references for gateway-normalized transient chat artifacts and safe attachment
error payloads. The chat graph accepts at most five references while keeping
file bytes and extracted document text outside graph state and stream events.
`ax-integrations` resolves only absolute `file://` paths below
`AX_CHAT_ARTIFACT_ROOT`, rejects traversal and symlinks, opens every path
component with no-follow semantics, and verifies regular-file type, size,
stability, and SHA-256 before constructing provider content. Documents become
delimited untrusted text parts; normalized PNG, JPEG, and WebP files become
base64 `image_url` parts only when `OPENAI_SUPPORTS_VISION=true`. Vision remains
disabled by default and must be enabled only after a live capability check.
The product backend requests only LangGraph `custom` stream mode for attachment
runs, preventing the runtime's initial values event from echoing private file
references; a terminal `response_complete` custom event verifies the assembled
answer. Text-only chat retains the existing `custom` plus `values` contract.

## 1. Design goals and constraints

The system must be clean, maintainable, fast, modular, secure, and suitable
for production workloads. The architecture therefore favors:

- explicit package boundaries and stable contracts;
- compiled LangGraph graphs with small, typed state;
- durable execution delegated to Agent Server and PostgreSQL;
- side effects isolated behind capability-scoped tools and integrations;
- a private Agent Server behind an authenticated product API gateway;
- deterministic tests and separate quality evaluations;
- bounded retries, timeouts, cancellation, and resumable interruptions;
- provider-neutral ports where changing model or infrastructure vendors does
  not change graph topology.

LangGraph is the orchestration runtime, not the entire application framework.
LangChain integrations may be used inside adapters, while LangSmith remains an
optional tracing and evaluation backend. [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)

## 2. Runtime topology

```text
Client
  |
  v
API Gateway (public boundary)
  |  AuthN/AuthZ, tenant policy, limits, audit, API contracts
  v
Agent Server (private)
  |  assistants, threads, runs, streaming, task queue
  +--> PostgreSQL (durable resources, checkpoints, long-term store)
  +--> Redis (ephemeral queue signaling, cancellation, pub/sub)
  +--> SearXNG (private, no-provider-key web discovery)
  |
  v
Compiled LangGraph graphs
  +--> supervisor/coordinator nodes
  +--> specialist subgraphs
  +--> capability-scoped tool adapters
  +--> model and external-service integrations
```

The first production target is self-hosted Agent Server on Docker Compose or
a VM. Compose is the local/integration baseline; the container boundaries and
configuration must remain portable to Kubernetes. LangChain documents
PostgreSQL and Redis as required standalone-server backing services and
recommends Kubernetes for production-grade scaling, but this project selects
Compose/VM as its initial operational target. [Standalone deployment](https://docs.langchain.com/langsmith/deploy-standalone-server)

Agent Server is not publicly exposed. The gateway translates the product API
into Agent Server calls and owns user-facing security policy. This prevents
clients from coupling to LangGraph-specific API details.

## 3. Repository and package structure

```text
apps/
  gateway/                   # public API service
  agent_server/              # Agent Server deployment metadata
  workers/                   # independently scalable async execution boundary
workflows/
  orchestrator/              # optional cross-workflow dynamic delegation
  smoke/                     # deterministic example graph
  risk_monitoring/           # business workflow graph
  weekly_report/
  call_recommendation/
  device_management/
packages/
  contracts/                 # versioned Pydantic boundary models
  runtime/                   # execution context, limits, normalized errors
  tools/                     # tool policies and capability contracts
  integrations/              # model, Agent Server, storage, HTTP ports
  persistence/               # durable storage ports and adapters
  observability/             # logs, metrics, traces, and audit boundaries
  evals/                     # datasets, evaluators, release gates
infra/
  compose/                   # local and VM Agent Server topology
tests/
  unit/                      # isolated deterministic behavior
  contract/                  # schema and boundary compatibility
  integration/               # PostgreSQL, Redis, Agent Server containers
  evals/                     # quality and trajectory regression cases
docs/
```

The root is a `uv` workspace. Each package has its own `pyproject.toml`,
editable workspace dependency, focused tests, and minimal runtime dependencies.
Dependencies may flow only in the following direction:

```text
apps -> workflows -> packages
apps ----------------> packages

packages/runtime --------> packages/contracts
packages/tools ----------> packages/contracts
packages/integrations ---> packages/contracts
packages/persistence ----> packages/contracts
packages/observability --> packages/contracts
packages/evals ----------> packages/contracts
```

Shared packages never import from `apps/` or `workflows/`. Apps may compose
workflows and packages. Workflow-local prompts, state, nodes, specialists, and
topology stay in `workflows/<name>/`; provider clients stay in
`packages/integrations`; reusable capability policy stays in
`packages/tools`; external request handling stays in `apps/gateway`.

This is a modular monolith, not a service per workflow. Split an application
or worker deployment only when ownership, isolation, load, or availability
measurements justify the operational cost.

## 4. Contracts and state

`ax-contracts` is the only source of cross-boundary schemas. Models reject
unknown fields and carry `schema_version` so persisted or replayed results can
be migrated deliberately.

Required contracts are:

- `TaskEnvelope`: objective, context, priority, task identity, requester;
- `RunContext`: tenant, thread, run, correlation identity, deadline, attempt;
- `AgentInput` / `AgentOutput`: validated graph boundary and evidence;
- `ToolRequest` / `ToolResult`: capability, arguments, idempotency, risk, and
  retry classification;
- `Handoff`: source/target ownership, objective, artifacts, evidence, and stop
  conditions;
- `ArtifactRef`: URI, type, version, and optional checksum;
- `ChatAttachmentRef`: transient attachment identity, safe filename, kind,
  normalized media type, local file URI, byte size, and SHA-256;
- `ChatErrorPayload`: safe attachment/capability error code, message, and
  optional affected filename for custom stream events and terminal chat state;
- `EvaluationResult`: criterion, status, severity, score, evidence, and
  recommendation.
- `WeeklyReportRequest`, `WardWeeklyMetricSnapshot`, `WardWeeklyMetricDelta`,
  `WardWeeklyMetrics`, `WardWeeklyReport`, and `WardWeeklyReportBatchResult`:
  the versioned selection input, full current/prior ward metadata, grounded
  narrative, Markdown output, and ordered batch result for
  `ansimk_weekly_reporter`. `WeeklyReportSourceResponse` is the private
  FastAPI-to-workflow snapshot boundary. Earlier
  personal-work contracts remain temporarily exported for compatibility.

LangGraph state should contain only the minimum working state needed by the
graph. Durable state must be associated with a stable `thread_id`; checkpoint
history and task writes are relied on for resumption and failure recovery.
[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

## 5. Graph and agent design

- Export compiled graphs from `workflows/`; use factories only when a run needs
  graph customization.
- Keep nodes small and testable. Nodes decide and transform state; tools perform
  controlled side effects.
- Use explicit edges, bounded loops, maximum step/tool-call limits, and terminal
  states (`completed`, `blocked`, `failed`).
- Use a supervisor graph only when work spans multiple specialists. Each
  specialist has a responsibility, authority, inputs, outputs, tools,
  stop-conditions, and escalation rule.
- Require handoffs to carry structured output, artifacts, evidence, and the
  next action; never hand off an unbounded transcript as the only contract.
- Use `interrupt()` for approval or missing human input. A persistent
  checkpointer and stable thread ID are mandatory for resumable interrupts; use
  a production checkpointer rather than in-memory storage. [Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- Do not instantiate production checkpointers or stores inside graph modules;
  Agent Server injects those resources at deployment time. [Agent Server persistence](https://docs.langchain.com/langsmith/agent-server)
- `ansimk_weekly_reporter` uses a coordinator plus isolated per-ward subgraph.
  The coordinator calls only its private-network source API and `Send`
  fans out after source and reporting-window validation. Branches transform
  verified metrics into report-facing section results, request one Korean
  summary paragraph,
  validate or replace it, and return finalized reports through reducers.
  Source selection accepts explicit ward IDs or an opaque validated cursor and
  is capped at twenty-five. Operator-facing callers execute one branch at a
  time to preserve interactive model capacity; isolated tests may raise that
  bound, while the separate bulk worker owns high-throughput concurrency.

## 6. Gateway API

The public API is versioned and intentionally independent of Agent Server wire
schemas:

| Endpoint | Behavior |
| --- | --- |
| `POST /v1/runs` | Validate and submit a task; return run identity and status. |
| `GET /v1/runs/{run_id}` | Return normalized status, output, errors, and evidence. |
| `GET /v1/runs/{run_id}/events` | Stream progress and terminal events. |
| `POST /v1/threads/{thread_id}/resume` | Resume a durable interrupt with a validated command. |
| `GET /healthz` / `GET /readyz` | Liveness and dependency readiness. |

Gateway responsibilities include authentication, authorization, tenant
isolation, request size/rate limits, idempotency keys, correlation IDs, audit
events, input/output redaction, and mapping internal errors to safe public
responses. The gateway must not expose provider credentials, raw stack traces,
raw prompts, or unrestricted tool arguments.

## 7. Tools and integrations

Tools are registered by capability and risk (`read`, `write`, `destructive`).
Every call is checked against a tenant-aware allowlist before execution.

Tool adapters must define:

- typed arguments and results;
- timeout and cancellation behavior;
- idempotency strategy;
- retryable versus permanent error mapping;
- audit metadata;
- network and credential scope.

Secrets remain in the executor/integration layer and are never inserted into
prompts or agent-visible state. External input and model output are untrusted
until validated.

The OpenAI-compatible model adapter accepts `URL`, `MODEL`, and
`OPENAI_API_KEY`, with `OPENAI_BASE_URL` and `OPENAI_MODEL` as preferred aliases
for shared environments. It normalizes server, `/v1`, and full completion URLs;
uses streamed SSE responses; reuses a bounded async connection pool; and
retries transient failures only before any response content has been emitted.
Provider errors must not expose credentials or unrestricted response bodies.
Its provider-neutral message contract accepts either text or validated
OpenAI-compatible text/image content parts. Remote image URLs are rejected;
image inputs use data URLs assembled transiently from verified normalized
artifacts. `OPENAI_SUPPORTS_VISION` defaults to false and is a deployment
capability assertion, not automatic model detection.

The transient chat attachment reader is an integration boundary because it
owns filesystem access and provider-payload assembly. The gateway passes only
`ChatAttachmentRef` objects. The reader enforces five files, 10 MiB per file,
25 MiB combined, and 100,000 extracted document characters. It accepts
normalized UTF-8 plain/Markdown/CSV text and normalized PNG/JPEG/WebP bytes.
Every attachment and original filename is explicitly labeled untrusted in the
model request so multi-file prompts can still refer to files by name.

Reusable web research is split into discovery and evidence retrieval.
`web_search` calls an injected provider-neutral executor; the initial adapter
uses a private SearXNG JSON API and returns normalized, deduplicated source
metadata. `web_fetch` opens one selected public HTTP(S) source and returns
bounded readable text marked as untrusted. Both tools are read-risk operations,
require explicit allowlisting, produce deterministic idempotency keys, preserve
stable source IDs and URLs for citations, and propagate cancellation.

Page retrieval must resolve and pin public destinations, reject any DNS answer
set containing a non-global address, revalidate redirects, disable ambient
proxy configuration, omit user credentials and cookies, restrict content
types, and cap redirects, downloaded bytes, and extracted text. Search snippets
are discovery data only; workflows fetch selected pages before using
substantive claims as evidence. Retrieved content never changes permissions or
tool policy.

Remote MCP servers are declared in `config/mcp_servers.json`. Checked-in
configuration may name a secret environment variable and a non-secret prefix,
but may not contain a static credential. Discovered tools are namespaced by
server, validated against their advertised input JSON Schema, explicitly
classified by risk, and separately allowlisted by each consuming workflow.
Unclassified tools fail closed. Remote descriptions and results are untrusted;
they never modify permissions. MCP tool calls are not retried automatically
because remote idempotency cannot be assumed.

Reusable PostgreSQL access is exposed by `ax-integrations` as a bounded
`asyncpg` pool. It accepts only application-owned parameterized query strings,
runs each fetch in a read-only transaction, maps provider failures to safe
errors, and keeps DSNs out of graph state. The weekly reporter is the first
consumer through its private FastAPI process; it does not expose a
model-callable SQL tool.

Outbound Slack messaging is also exposed by `ax-integrations`, using the
official async Slack Web API client. Only channel IDs loaded from
`SLACK_DEFAULT_CHANNEL_ID` or `SLACK_CHANNEL_<NAME>` are authorized. Callers
receive a typed success/failure result; provider exceptions, tokens, message
text, blocks, and caller metadata are excluded from logs and normalized errors.
Slack rate-limit handling is bounded, `chat.postMessage` requests have a
configurable timeout, and tests inject a fake client. Business workflows must
call this service instead of importing the Slack SDK. Sensitive outbound
notifications retain their workflow-specific human-approval gate.

## 8. Persistence, reliability, and performance

- PostgreSQL is the durable system of record for Agent Server resources,
  checkpoints, thread state, and long-term memory.
- Redis stores ephemeral queue signaling, cancellation, and streaming pub/sub;
  no irreplaceable state may depend on Redis.
- Use bounded retries with explicit retry reasons, exponential backoff, and
  idempotent writes.
- Persist enough state to resume after worker interruption without rerunning
  completed side effects.
- Use deadlines, per-node/tool timeouts, cancellation, graceful shutdown, and
  duplicate-submission handling.
- Prefer compiled graphs, async I/O, small state payloads, bounded concurrency,
  and parallel fan-out only for independent work.
- Store large documents and generated artifacts outside graph state and pass
  typed references across nodes and handoffs.
- Chat attachments remain in a private shared transient volume. The graph reads
  them only for the active model call; normalized bytes, extracted text, and
  image data URLs are never returned in state or custom events. Attachment
  references are cleared from terminal state after success or safe failure.
- Reuse bounded HTTP and database connection pools in adapters; never create a
  client per node invocation.
- Track queue delay separately from graph execution time and model/tool latency.

Agent Server supports single-host and split API/queue modes. Begin with the
single-host Compose baseline, then separate API and queue workers when load
requires independent scaling. [Agent Server runtime architecture](https://docs.langchain.com/langsmith/agent-server)

## 9. Security and observability

- Authenticate every public request and authorize every tenant/resource action.
- Keep gateway and Agent Server on private network segments; use TLS at the
  ingress boundary.
- Load secrets from deployment secret stores; never commit `.env` secrets,
  bake them into images, or print them.
- Redact sensitive inputs, outputs, metadata, and tool arguments before tracing;
  disable tracing for data classes that cannot be safely retained. [Trace masking](https://docs.langchain.com/langsmith/mask-inputs-outputs)
- Emit structured events for request, assignment, node start/end, tool call,
  retry, interrupt, resume, evaluation, and completion.
- Include correlation, tenant, thread, run, graph, node, and version metadata
  without including secrets or unrestricted user content.
- Measure latency, queue time, throughput, errors, retries, token usage, cost,
  checkpoint failures, and evaluation scores.

## 10. Verification and release gates

Every package must have unit tests. Shared behavior additionally requires:

- contract tests rejecting malformed or unknown fields;
- graph tests for happy path, bounded loops, failure, and interrupt/resume;
- tool-policy tests for allow, deny, timeout, and destructive actions;
- gateway tests for auth boundary, validation, idempotency, and safe errors;
- container integration tests with PostgreSQL, Redis, and Agent Server;
- recovery tests for worker restart, duplicate work, stale resume, and partial
  writes;
- curated evaluation datasets for task success, tool selection, argument
  correctness, safety, cost, latency, and trajectory quality.

CI must run formatting, linting, type checks, dependency/security audit,
contract/unit tests, integration tests, and evaluation thresholds before image
publication. LangSmith evaluations may be used for offline, online, and CI
quality gates while keeping evaluator interfaces provider-neutral. [Evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)

## 11. Implementation order

1. Keep `ax-contracts` and package dependency checks stable.
2. Add runtime context, error, limit, and retry primitives.
3. Add graph package conventions and one deterministic compiled graph.
4. Add tool policy and one fake integration for contract tests.
5. Add gateway adapter and public API tests.
6. Add PostgreSQL/Redis Compose integration and Agent Server image build.
7. Add persistence recovery, interrupt/resume, observability, and security
   checks.
8. Add and mock-test real model/tool integrations as workflows require them;
   require the preceding deployment gates plus live readiness checks before
   production release.

## 12. Known limitations and decisions deferred

- The weekly reporter now calculates broad raw weekly metadata and produces
  validated warm Korean summaries. It remains manually triggered and does not
  schedule or persist rendered reports. An operator can explicitly deliver a
  completed batch to an approved Slack destination; delivery is not
  an automatic graph side effect. Weekly-average risk-score bands and indoor
  environment ranges are product-approved deterministic presentation rules;
  the weekly-summary model receives neither numeric score nor report-facing
  overall/basic-information values. The
  model-backed chat workflow remains a
  one-turn path and does not yet compose the reusable web research tools. Chat
  attachments are transient and cannot be referenced by later turns;
  scanned-PDF OCR and durable or multi-host artifact storage remain outside the
  agent runtime.
- MCP registry, discovery, and authorized tool adapters are implemented. The
  weekly reporter no longer grants an MCP tool; other workflows receive
  no MCP capabilities unless they define their own minimal allowlist and
  tool-use behavior.
- No-key SearXNG engines may be throttled, challenged by CAPTCHAs, or change
  without notice. Their live quality is monitored separately from deterministic
  CI and is not equivalent to a paid search-provider availability contract.
- `apps/workers`, `packages/persistence`, and `packages/observability` are
  explicit extension boundaries; their production implementations remain
  intentionally deferred until requirements and load measurements exist.
- Compose/VM is the selected first production posture; Kubernetes remains the
  scale-out migration target.
- LangSmith tracing/evaluation is optional and must be configured only after
  data-retention and redaction policy is approved.
- Concrete tenant model, identity provider, database HA strategy, and model
  vendor remain application decisions, but must not violate these boundaries.
