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

The current workflow collection contains a deterministic smoke graph:

```python
from workflows.smoke import graph

graph.invoke({"message": "hello"})
```

Future business agents belong here. Graphs should call tools and integrations
through interfaces rather than embedding infrastructure code.

Each workflow is a vertical module that owns its `graph.py`, minimal
`state.py`, nodes, optional local agents and prompts, and workflow policy. The
smoke workflow demonstrates the minimum `graph`/`state`/`nodes` separation.

## `ax-tools`

The capability and permission layer.

It owns tool registration, typed tool boundaries, allowlists, read/write/
destructive risk classification, authorization, and future tool timeout,
retry, and audit metadata.

The current implementation provides `ToolPolicy` and `authorize()`. An agent
must not freely invoke an unapproved tool or destructive operation.

## `ax-integrations`

The external-system adapter layer.

It owns Agent Server clients, model-provider adapters, databases, stores, HTTP
APIs, queues, filesystems, and translation of external failures into internal
contracts.

The current implementation defines the `AgentServerClient` protocol for
submitting runs, reading status, streaming events, and resuming interrupted
threads. Production adapters are still to be implemented here.

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

The current package only exposes the shared `EvaluationResult` contract.
Datasets and evaluators will be added with the first business-specific agent.

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

- The graph is provider-neutral and not a business agent yet.
- The Agent Server adapter and authentication provider are not implemented.
- Durable production persistence and real external tools are not configured.
- Evaluation datasets and automated quality gates are not yet present.
