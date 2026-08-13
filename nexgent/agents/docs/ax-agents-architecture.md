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
- Agent Server adapter port and FastAPI gateway with health, submit, status,
  SSE events, and interrupt-resume route contracts;
- self-hosted PostgreSQL/Redis/Agent Server Compose baseline;
- pooled asynchronous OpenAI-compatible model adapter and one-turn chat graph;
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
- `EvaluationResult`: criterion, status, severity, score, evidence, and
  recommendation.
- `WeeklyReportRequest`, `WeeklyMetricSnapshot`, `WeeklyMetricDelta`,
  `UserWeeklyMetrics`, `UserWeeklyReport`, and `WeeklyReportBatchResult`: the
  versioned input, deterministic calculations, personal Markdown output, and
  ordered batch result for `ansimk_weekly_reporter`.

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
- `ansimk_weekly_reporter` uses a coordinator plus isolated per-user subgraph.
  `Send` fans out only after repository validation, and branches return only
  finalized reports and warnings through reducers. Default callers bound
  execution to four concurrent tasks, while the graph rejects more than one
  hundred users per batch.

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

- The weekly reporter is the first business-specific workflow, but uses mock
  work-activity records and only returns/display reports. Its database,
  scheduler, persistence, authentication, and delivery adapters are not yet
  implemented. The model-backed chat workflow remains a minimal one-turn path
  and does not yet compose the reusable web research tools.
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
