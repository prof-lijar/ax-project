# Scalable Agent Platform Structure

Date: 2026-08-05

## Purpose

This implementation record documents the move to a scalable modular-monolith
foundation for many LangGraph workflows. It does not assume that AX is limited
to risk handling. The authoritative rules remain in
[AX agents architecture](ax-agents-architecture.md).

## Implemented structure

```text
agents/
├── apps/                              # deployable process boundaries
│   ├── agent_server/
│   │   └── README.md                  # Agent Server deployment contract
│   ├── gateway/                       # public product API
│   │   ├── __init__.py                # gateway public exports
│   │   ├── app.py                     # FastAPI routes and app factory
│   │   └── main.py                    # ASGI application entrypoint
│   └── workers/
│       └── README.md                  # future independently scaled workers
│
├── workflows/                         # business capability modules
│   ├── orchestrator/
│   │   └── README.md                  # optional cross-workflow coordination
│   ├── smoke/                         # complete executable reference path
│   │   ├── __init__.py                # exports the compiled graph
│   │   ├── graph.py                   # topology and compiled graph entrypoint
│   │   ├── nodes.py                   # workflow-owned node functions
│   │   └── state.py                   # minimal typed graph state
│   ├── risk_monitoring/
│   │   └── README.md                  # workflow contract placeholder
│   ├── weekly_report/
│   │   └── README.md                  # workflow contract placeholder
│   ├── call_recommendation/
│   │   └── README.md                  # workflow contract placeholder
│   ├── device_management/
│   │   └── README.md                  # workflow contract placeholder
│   ├── __init__.py
│   └── README.md                      # required workflow module convention
│
├── packages/                          # reusable business-neutral libraries
│   ├── contracts/
│   │   ├── pyproject.toml             # ax-contracts package metadata
│   │   └── src/ax_contracts/
│   │       ├── __init__.py            # versioned contract exports
│   │       └── models.py              # task, run, tool and handoff schemas
│   ├── runtime/
│   │   ├── pyproject.toml             # ax-runtime package metadata
│   │   └── src/ax_runtime/
│   │       ├── __init__.py
│   │       ├── errors.py              # normalized runtime errors
│   │       └── execution.py           # limits, context and graph config
│   ├── tools/
│   │   ├── pyproject.toml             # ax-tools package metadata
│   │   └── src/ax_tools/
│   │       ├── __init__.py
│   │       └── policy.py              # capability/risk authorization
│   ├── integrations/
│   │   ├── pyproject.toml             # ax-integrations package metadata
│   │   └── src/ax_integrations/
│   │       ├── __init__.py
│   │       └── agent_server.py        # Agent Server adapter protocol
│   ├── persistence/
│   │   ├── pyproject.toml             # ax-persistence package metadata
│   │   └── src/ax_persistence/
│   │       └── __init__.py            # durable storage extension boundary
│   ├── observability/
│   │   ├── pyproject.toml             # ax-observability package metadata
│   │   └── src/ax_observability/
│   │       └── __init__.py            # telemetry/audit extension boundary
│   └── evals/
│       ├── pyproject.toml              # ax-evals package metadata
│       └── src/ax_evals/
│           └── __init__.py            # evaluation contract exports
│
├── tests/                              # shared verification by intent
│   ├── unit/
│   │   ├── test_boundaries.py         # gateway behavior tests
│   │   └── test_graph.py              # deterministic workflow tests
│   ├── contract/
│   │   ├── test_contracts.py          # schema validation tests
│   │   └── test_dependency_boundaries.py # import-direction enforcement
│   ├── integration/
│   │   └── README.md                  # container/infrastructure test scope
│   └── evals/
│       └── README.md                  # behavioral evaluation test scope
│
├── infra/
│   └── compose/
│       ├── .env.example               # non-secret configuration template
│       ├── docker-compose.yml          # PostgreSQL/Redis/Agent Server stack
│       └── README.md                   # stack operating instructions
│
├── docs/
│   ├── README.md                      # documentation map
│   ├── ax-agents-architecture.md      # authoritative architecture
│   ├── ax-agents-module-guide.md      # module responsibilities
│   ├── langgraph-environment-setup.md # environment implementation record
│   └── scalable-agent-platform-structure.md # this structure record
│
├── AGENTS.md                          # mandatory contributor/agent rules
├── README.md                          # workspace quick start
├── langgraph.json                     # deployable graph registrations
├── pyproject.toml                     # root project and uv workspace config
└── uv.lock                            # reproducible dependency lock
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
