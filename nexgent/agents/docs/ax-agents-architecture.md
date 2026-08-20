# AX Agents Architecture

Date: 2026-08-05

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
may produce only validated, digit-free prose. Model configuration, request,
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

Weekly Reporter frontend integration update on 2026-08-19: the catalog route
`/agents/1` owns the live workbench again, while `/test-agent` remains an alias
for isolated testing. An operator-triggered request sends an explicit limit of
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

Weekly Reporter environment-policy update on 2026-08-20: a product-approved,
deterministic presentation rule now classifies weekly indoor extrema using the
reporting week's starting month. Temperature ranges are 18–20℃ for
January–March and November–December, 20–22℃ for April–May and October, and
26–28℃ for June–September; humidity is 40–60% year-round. Python converts
below/above-bound measurements into cold/hot or dry/humid qualitative facts.
The reporter prompt requires those facts in `analysis_text`, and validation
enforces the required topic without exposing numeric values to the model.

Frontend launch integration update on 2026-08-14: the Agents catalog marks
`ansimk_weekly_reporter` as the single live-data entry. Both of its **Run in
Chat** actions create a one-shot run intent in UI state and navigate to Chat.
Chat consumes that intent once, chooses the most recent completed Monday in
the local calendar with `Asia/Seoul`, and calls the existing Agent Server SSE
boundary with cancellation enabled. Custom workflow events drive a live
four-stage trace; the completed per-ward Markdown reports and any warnings are
rendered in the transcript. Frontend parsing mirrors the ward danger-day
contract and rejects malformed events or results. The browser stores no MCP
endpoint or credential. Other preview agents still have no live runner.

Weekly Reporter detail integration update on 2026-08-14: the stable catalog
route `/agents/1` now renders the live `ansimk_weekly_reporter` workbench
directly. Operators can select a reporting Monday and timezone, observe
validated custom progress events, cancel the active Agent Server run, and
inspect per-ward Markdown and metrics without leaving the agent detail route.
The existing `/test-agent` route reuses the same workbench in test-oriented
presentation, while all other agent detail routes retain their preview UI.

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
  verified metrics into qualitative facts, request structured Korean prose,
  validate or replace it, and return finalized reports through reducers.
  Source selection accepts explicit ward IDs or an opaque validated cursor and
  is capped at twenty-five; callers bound branch execution to four concurrent
  tasks.

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
  an automatic graph side effect. Risk-score meaning remains intentionally
  undefined. The approved indoor environment ranges are the only current
  business thresholds, and the model receives only their deterministic
  qualitative result. The model-backed chat workflow remains a
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
