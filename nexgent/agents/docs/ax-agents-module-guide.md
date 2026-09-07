# AX Agents Module Guide

Date: 2026-08-05

This guide explains the responsibilities and boundaries of the modular AX
agents packages. The authoritative architectural rules remain in
[ax-agents-architecture.md](ax-agents-architecture.md); read that document
before changing package boundaries or runtime behavior.

## Dependency flow

```text
apps/gateway
    |
    v
packages/integrations ---> Agent Server, models, and external services
    |
    v
workflows/ ---> packages/runtime ---> packages/contracts
    |
    v
packages/tools
    |
    v
ax-evals

packages/persistence and packages/observability also depend inward on
packages/contracts and remain independent of individual workflows.
```

`ax-contracts` is the shared foundation. It defines typed schemas such as
`RunContext`, `TaskEnvelope`, `ToolRequest`, `Handoff`, and
`EvaluationResult`.

## `ax-runtime`

The execution reliability layer.

It owns correlation and tenant context, thread/run identity, execution
deadlines and limits, normalized runtime errors, retryability classification,
and LangGraph configuration helpers. Future checkpoint, cancellation,
recovery, and retry utilities belong here.

Current public pieces include `ExecutionLimits`, `AgentRuntimeError`,
`ErrorCode`, and `build_config()`.

It must not contain business prompts, agent roles, or external API clients.

## `workflows/` (agent/workflow layer)

The LangGraph graph layer.

It owns compiled graphs, supervisor/coordinator graphs, specialist subgraphs,
graph state, routing, stopping logic, prompts, and agent-specific behavior.

The workflow collection contains a deterministic smoke graph:

```python
from workflows.smoke import graph

graph.invoke({"message": "hello"})
```

Future business agents belong here. Graphs should call tools and integrations
through interfaces rather than embedding infrastructure code.

The `workflows/chat` graph is the first LLM-backed vertical path. It accepts
one message, invokes the shared OpenAI-compatible adapter asynchronously, and
returns the generated response. It is intentionally separate from `smoke` so
model availability does not affect deterministic runtime checks.

The `workflows/weekly_report` graph is the first business-specific workflow.
It loads bounded current/prior metadata from the private weekly-report FastAPI
source, fans out per ward, converts validated metrics to qualitative facts,
limits the model to a grounded Korean outline covering activity, indoor
environment, and device reception with only allowlisted significant numeric
tokens, and merges Markdown reports deterministically.
Model or narrative validation failures use a
disclosed warm template fallback. Scheduling, persistence, delivery, and
risk-score interpretation remain outside the generation graph. A separate
workflow-local Slack delivery module accepts only completed validated batches,
uses the shared integration service and an approved default or configured
logical destination, and requires explicit human approval before sending
care-related content.

Each workflow is a vertical module that owns its `graph.py`, minimal
`state.py`, nodes, optional local agents and prompts, and workflow policy. The
smoke workflow demonstrates the minimum `graph`/`state`/`nodes` separation.

## `ax-tools`

The capability and permission layer.

It owns tool registration, typed tool boundaries, allowlists, read/write/
destructive risk classification, authorization, and future tool timeout,
retry, and audit metadata.

The current implementation provides `ToolPolicy`, `authorize()`, and reusable
`web_search`/`web_fetch` `StructuredTool` factories. The factories accept
provider-neutral executors, authorize each read-risk call, attach deterministic
idempotency, and return normalized artifacts. An agent must not freely invoke
an unapproved tool or destructive operation.
It also converts discovered MCP tool definitions into collision-safe,
namespaced `StructuredTool` instances. Remote JSON Schemas are checked locally,
unclassified tools fail closed, and every call passes through the same
allowlist and read/write/destructive policy.

## `ax-integrations`

The external-system adapter layer.

It owns Agent Server clients, model-provider adapters, databases, stores, HTTP
APIs, queues, filesystems, and translation of external failures into internal
contracts.

The current implementation defines the `AgentServerClient` protocol for
submitting runs, reading status, streaming events, and resuming interrupted
threads. It also provides a pooled asynchronous OpenAI-compatible chat adapter
with SSE parsing, bounded retries, safe provider errors, and environment-based
configuration. The real Agent Server client remains to be implemented.
It also provides a pooled SearXNG search adapter and an SSRF-safe public-page
fetch adapter with bounded extraction. These adapters satisfy the web tool
ports without making tools or workflows depend on SearXNG.
The MCP integration adds a strict JSON server registry, environment-only HTTP
header sources, pooled Streamable HTTP clients, paginated tool discovery,
normalized untrusted call results, and a safe inspection CLI. The first entry
is the read-only `db_mcp_server`; workflows still choose and allowlist its tools
explicitly.
The PostgreSQL integration adds an environment-backed `asyncpg` pool whose
application-owned queries run inside read-only transactions. The weekly-report
FastAPI process is its first consumer; the graph and model never receive its
DSN or an arbitrary SQL capability.
The outbound Slack integration wraps the official asynchronous Slack SDK behind
typed message/result dataclasses. It validates text, blocks, thread timestamps,
timeouts, and channel IDs; approves only configured default or logical
destinations; performs one bounded rate-limit retry; and logs delivery status
without tokens, content, metadata, or raw provider errors. Agents and workflows
must use this service rather than importing `slack_sdk` directly.

## `apps/gateway`

The public API boundary.

It owns authentication and authorization, tenant isolation, request
validation, rate limits, idempotency, audit logging, safe errors, and
translation between product APIs and Agent Server APIs.

Current routes are:

| Route | Purpose |
| --- | --- |
| `GET /healthz` | Liveness check |
| `POST /v1/runs` | Submit a run |
| `GET /v1/runs/{run_id}` | Read run status |
| `GET /v1/runs/{run_id}/events` | Stream run events |
| `POST /v1/threads/{thread_id}/resume` | Resume an interrupted run |

The default gateway returns `503` until a real Agent Server adapter is
configured. Agent Server should remain private; clients should use this
gateway instead of depending directly on LangGraph APIs.

## `apps/weekly_report_api`

The private weekly-report source boundary. It owns source request/response
validation, pooled database lifecycle, readiness, and safe database-error
mapping. Its business calculations remain
workflow-owned under `workflows/weekly_report/source`; the app composes and
serves them without exposing generic database access.

## `apps/workers`

The independently scalable background-execution deployment boundary. It is
reserved until queue pressure or latency measurements justify separating API
and worker processes; the initial Agent Server topology stays single-host.

## `ax-persistence`

The durable storage boundary for application-owned execution records,
artifacts, repositories, and future storage adapters. LangGraph/Agent Server
checkpoint injection remains deployment-owned. This package must not contain
workflow decisions.

## `ax-observability`

The structured logs, metrics, traces, and audit-event boundary. It will own
provider-neutral telemetry interfaces and redaction hooks, not business
evaluation criteria or provider credentials.

## `ax-evals`

The quality and release-gate layer.

It owns evaluation datasets, deterministic contract checks, trajectory and
tool-use evaluation, LLM-as-judge evaluators, regression comparisons, CI/CD
thresholds, and production feedback analysis.

The current package exposes the shared `EvaluationResult` contract plus
deterministic weekly-report evaluators for batch completeness, Korean Markdown
structure, identity, metric grounding, and fallback disclosure. Broader
datasets and online evaluation remain future work.

## Practical ownership rule

- Runtime reliability belongs in `ax-runtime`.
- Agent and workflow behavior belongs in `workflows/`.
- Capability authorization belongs in `packages/tools`.
- External infrastructure belongs in `packages/integrations`.
- Durable storage implementations belong in `packages/persistence`.
- Telemetry and audit boundaries belong in `packages/observability`.
- Public HTTP behavior belongs in `apps/gateway`.
- Quality decisions belong in `packages/evals`.

When a change appears to fit multiple packages, keep the smallest stable
interface in `ax-contracts` and place the implementation in the package that
owns the behavior.

## Current limitations

- The LLM chat graph is a minimal one-turn integration, not a business agent.
- The Agent Server adapter and authentication provider are not implemented.
- Durable production persistence and business-specific tools are not
  configured; reusable public-web research is the first real read-only tool
  capability.
- Weekly-report deterministic evaluators now gate batch completeness, Korean
  Markdown structure, personalization, numeric grounding, and fallback
  disclosure. Broader production datasets and online quality gates remain
  future work.
