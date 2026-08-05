# Scalable Agent Platform Structure

Date: 2026-08-05

## Purpose

This implementation record documents the move to a scalable modular-monolith
foundation for many LangGraph workflows. It does not assume that AX is limited
to risk handling. The authoritative rules remain in
[AX agents architecture](ax-agents-architecture.md).

## Implemented structure

```text
apps/
  gateway/          # public product API
  agent_server/     # LangGraph Agent Server deployment metadata
  workers/          # future independently scalable background execution
workflows/
  orchestrator/     # optional cross-workflow coordination
  smoke/            # executable reference workflow
  risk_monitoring/
  weekly_report/
  call_recommendation/
  device_management/
packages/
  contracts/        # versioned cross-boundary schemas
  runtime/          # execution context, limits, recovery primitives
  tools/            # capability and authorization policy
  integrations/     # external provider and service adapters
  persistence/      # durable storage ports and adapters
  observability/    # logs, metrics, traces, audit boundaries
  evals/            # quality evaluation and release gates
tests/
  unit/
  contract/
  integration/
  evals/
```

The former top-level `graphs/` directory is now `workflows/`. The name makes
the ownership boundary explicit: a workflow may contain deterministic nodes,
agent nodes, specialist subgraphs, human approvals, and tools. A graph is its
runtime topology, not necessarily one agent.

The executable smoke workflow was split into `graph.py`, `state.py`, and
`nodes.py`. `langgraph.json`, imports, commands, and tests now use
`workflows.smoke`.

## Architecture decisions

### Modular monolith first

The repository supports multiple deployable processes without making each
workflow a microservice. This keeps local development, refactoring, and shared
contract changes fast. A process is split only for measured load, availability,
security isolation, or independent ownership.

### Vertical workflow ownership

Every `workflows/<name>/` module owns its graph topology, minimal state, nodes,
local specialist agents, prompts, and workflow-specific policy. Optional
folders are created only when used. Shared infrastructure and business-neutral
code must move to a package instead of being copied between workflows.

### Inward dependency direction

```text
apps -> workflows -> packages -> contracts
apps ----------------> packages
```

Packages never import applications or workflows. This prevents circular
dependencies and allows shared packages to be tested and reused independently.

### Performance rules

Performance is enforced through runtime behavior rather than directory names:

- compile graph topology once;
- keep graph state small and pass artifact references instead of documents;
- use asynchronous external I/O and shared bounded connection pools;
- run only independent branches concurrently and enforce concurrency limits;
- keep deterministic routing and validation out of model calls;
- separate queue delay, graph time, model latency, and tool latency in metrics;
- split API and worker processes only after measurements show the need.

### Security and maintainability rules

- Tools remain capability-scoped and risk-classified.
- Provider credentials and clients remain outside workflow state and prompts.
- Cross-boundary data uses versioned contracts.
- Persistence and telemetry stay provider-neutral at their interfaces.
- Supervisors are introduced only for genuine dynamic delegation, with bounded
  steps and typed handoffs.

These constraints are now recorded in `AGENTS.md`, which requires future
contributors and coding agents to preserve the structure.

## Commands

```bash
uv sync --dev
uv run ruff check apps workflows packages tests
uv run pytest
uv run langgraph validate
uv run python -c 'from workflows.smoke import graph; print(graph.invoke({"message": "hello"}))'
```

## Validation

Validated on 2026-08-05:

```text
uv sync --dev                              -> resolved 93 packages
ruff check apps workflows packages tests  -> passed
pytest                                     -> 13 passed
langgraph validate                         -> valid, 1 graph found
direct workflows.smoke invocation          -> ack: hello
```

Pytest emitted Python 3.14 deprecation warnings from `pytest-asyncio`; they do
not indicate test failures but should be revisited when upgrading that
dependency. Container integration tests were not run because they require the
PostgreSQL, Redis, and Agent Server development stack. The remaining command
is:

```bash
docker compose --env-file infra/compose/.env.example \
  -f infra/compose/docker-compose.yml up --build
```

## Known limitations and follow-up

- `apps/workers` is an explicit deployment boundary, not a custom worker
  implementation yet.
- `ax-persistence` and `ax-observability` currently establish package ownership;
  concrete adapters will be added with their contracts and tests.
- Placeholder workflows have no business contracts or executable graph until
  acceptance criteria are defined.
- Before the first production workflow ships, add container integration tests,
  recovery tests, telemetry redaction tests, and evaluation thresholds.
