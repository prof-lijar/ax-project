# AX Agents Architecture

Date: 2026-08-05

Status: **Authoritative implementation specification**

This document is the required starting point for any material change to AX
agent runtime, graph orchestration, tools, APIs, persistence, deployment,
security, or evaluation. `AGENTS.md` requires contributors and agents to read
it before implementation and update it when architecture changes.

## Implementation status

The baseline described here is implemented as of 2026-08-05:

- `uv` workspace with contracts, runtime, agents, tools, integrations,
  gateway, and evaluations packages;
- versioned Pydantic contracts with strict unknown-field rejection;
- runtime context, execution limits, normalized errors, and LangGraph config
  helpers;
- deterministic compiled graph exported from `ax-agents` and configured in
  `langgraph.json`;
- capability/risk-based tool authorization policy;
- Agent Server adapter port and FastAPI gateway with health, submit, status,
  SSE events, and interrupt-resume route contracts;
- self-hosted PostgreSQL/Redis/Agent Server Compose baseline;
- architecture governance in `AGENTS.md` and this document.

Validation completed:

```text
ruff check packages src tests       -> passed
python -m pytest -q                  -> 11 passed
langgraph validate                  -> valid, 1 graph found
docker compose config               -> valid with .env.example
langgraph dev + POST /runs/stream   -> streamed ack: hello
```

The real Agent Server adapter, authentication provider, durable production
database, model provider, and business-specific tools remain intentionally
unimplemented. Compose image build and PostgreSQL/Redis integration tests are
the next verification gate.

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
packages/
  ax-contracts/
    src/ax_contracts/       # versioned Pydantic boundary models
  ax-runtime/
    src/ax_runtime/         # execution context, limits, normalized errors
  ax-agents/
    src/ax_agents/graphs/   # compiled graphs and supervisor/subgraphs
  ax-tools/
    src/ax_tools/            # tool policies, registries, adapters' contracts
  ax-integrations/
    src/ax_integrations/    # model, Agent Server, storage, HTTP ports
  ax-gateway/
    src/ax_gateway/          # public FastAPI boundary and adapter wiring
  ax-evals/
    src/ax_evals/            # datasets, evaluators, release gates
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
Packages may import only in the following direction:

```text
contracts <- runtime <- agents
contracts <- tools
contracts <- integrations
agents/tools/integrations <- gateway
contracts + agents + runtime <- evals
```

No package may import gateway code from graph or tool code. Prompts and graph
topology stay in `ax-agents`; provider clients stay in `ax-integrations`;
policy stays in `ax-tools`; external request handling stays in `ax-gateway`.

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

LangGraph state should contain only the minimum working state needed by the
graph. Durable state must be associated with a stable `thread_id`; checkpoint
history and task writes are relied on for resumption and failure recovery.
[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

## 5. Graph and agent design

- Export compiled graphs from `ax-agents`; use factories only when a run needs
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
8. Add real model/tool integrations and business-specific agents only after the
   preceding gates pass.

## 12. Known limitations and decisions deferred

- The current scaffold has no business-specific agent, model provider, or real
  external tool.
- Compose/VM is the selected first production posture; Kubernetes remains the
  scale-out migration target.
- LangSmith tracing/evaluation is optional and must be configured only after
  data-retention and redaction policy is approved.
- Concrete tenant model, identity provider, database HA strategy, and model
  vendor remain application decisions, but must not violate these boundaries.
