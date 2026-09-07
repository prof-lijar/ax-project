# LangGraph Environment Setup

Date: 2026-08-05 (runtime import check updated 2026-08-10)

## Purpose

This document records the first greenfield environment milestone for AX
agents. It validates LangGraph as the orchestration runtime without coupling
the smoke test to a model provider or a future business-agent design.

For the project-wide package, security, deployment, and verification rules,
read the [AX agents architecture](ax-agents-architecture.md) first.

LangGraph is a low-level runtime for long-running, stateful agents. Its core
production capabilities include durable execution, persistence, streaming,
and human-in-the-loop control. LangChain can provide model/tool integrations,
but LangGraph itself does not require LangChain.

Sources:

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph installation](https://docs.langchain.com/oss/python/langgraph/install)
- [LangGraph application structure](https://docs.langchain.com/langsmith/application-structure)

## Environment decisions

- Runtime: Python, with `requires-python >=3.11`; the current workstation
  Python 3.14.4 satisfies this requirement.
- Package manager: `uv`, with `uv.lock` committed for reproducibility.
- Initial graph: deterministic provider-neutral node; no model API key is
  required.
- Local server:
  `langgraph dev --host 192.168.0.18 --port 2024 --no-browser --n-jobs-per-worker 4`, using the
  in-memory Agent Server mode for development on the trusted LAN.
- Production hosting and persistence: intentionally deferred. The later
  architecture phase must choose LangSmith Cloud, self-hosted Agent Server, or
  another platform and define authentication, database, queue, and operational
  controls.

## Project contract

- `SmokeState` is a typed state dictionary with `message` input and `response`
  output fields.
- `acknowledge` rejects missing, non-string, and blank messages with
  `ValueError`.
- The compiled `graph` is the deployable graph entrypoint declared by
  `langgraph.json`.
- Because graph entries are file paths, their entrypoint modules use absolute
  `workflows.*` imports. LangGraph API 0.12.0 executes file entries without
  package context, so relative imports in those entrypoint files fail at
  startup even when `langgraph validate` succeeds.
- The graph has one explicit node and explicit `START`/`END` edges. This keeps
  the first runtime check small while establishing a contract future agents
  can extend.

## Setup and operation

```bash
uv sync --dev
uv run pytest
uv run python -c 'from workflows.smoke import graph; print(graph.invoke({"message": "hello"}))'
uv run langgraph --help
uv run langgraph dev --host 192.168.0.18 --port 2024 --no-browser --n-jobs-per-worker 4
```

The development server binds to `192.168.0.18:2024`, making it reachable from
other servers on the same network. With the server running, use either the
interactive Studio URL printed by the CLI or the API:

```bash
curl -s http://192.168.0.18:2024/docs
curl -s --request POST \
  --url http://192.168.0.18:2024/runs/stream \
  --header 'Content-Type: application/json' \
  --data '{"assistant_id":"agent","input":{"message":"hello"},"stream_mode":"values"}'
```

The local server guide explicitly describes this mode as development/testing
and recommends persistent infrastructure for production.

This development runtime uses noop authentication. Bind it to the LAN only on
a trusted network, restrict port 2024 at the firewall, and do not use this
listener as the public production boundary.

## Validation performed

Validated on 2026-08-05 with Python 3.14.4:

- `uv sync --dev`: resolved and installed 81 packages, including LangGraph
  1.2.10, LangGraph CLI 0.4.31, and LangGraph SDK 0.4.2.
- `uv run pytest`: 5 tests passed.
- Direct invocation returned `{'message': 'hello', 'response': 'ack: hello'}`.
- `uv run langgraph --help`: CLI loaded and exposed `dev`, `validate`,
  `build`, `up`, and related commands.
- `uv run langgraph validate`: configuration valid; one graph found.
- `uv run langgraph dev --no-browser --port 2024`: server started and imported
  graph `agent` successfully.
- `GET /docs`: succeeded.
- `POST /runs/stream`: streamed `{"message":"hello","response":"ack: hello"}`.

Revalidated on 2026-08-10 after adding the chat graph: both configured graph
files loaded under LangGraph API 0.12.0, `GET /ok` returned `{"ok":true}`, and
the smoke run streamed `{"message":"hello","response":"ack: hello"}`. A
contract test now reproduces the runtime's graph-entry import mode.

The first dependency attempt failed because the default uv cache directory was
read-only and the sandbox initially blocked DNS/socket access. The successful
validation used `UV_CACHE_DIR=/tmp/ax-langgraph-uv-cache` and the approved
network/socket escalation; this is an execution-environment workaround, not a
project requirement.

## Production follow-up

The local in-memory server must not be treated as a production deployment.
Before production agents are built, define and validate:

- persistent checkpoint and long-term memory stores;
- resumable execution, bounded retries, cancellation, and timeouts;
- authentication, secret handling, and tool permission boundaries;
- structured tracing, metrics, logs, and cost tracking;
- graph, tool, and output schemas with versioning and boundary validation;
- evaluator datasets, failure-path tests, and release gates;
- deployment topology, health checks, scaling, backups, retention, and incident
  recovery.

LangGraph's persistence documentation identifies PostgreSQL-backed checkpointing
as a production option, while Agent Server also requires PostgreSQL for core
threads/runs and provides a task queue in deployment environments.

Sources:

- [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Agent Server](https://docs.langchain.com/langsmith/agent-server)
- [Configure checkpointer backend](https://docs.langchain.com/langsmith/configure-checkpointer)
- [LangGraph CLI](https://docs.langchain.com/langsmith/cli)

## Known limitations

- An OpenAI-compatible model adapter and minimal chat graph are available; no
  real tools, business logic, memory policy, or multi-agent coordination is
  included yet.
- The local server uses in-memory state and is not durable across restarts.
- No LangSmith credentials or hosted deployment are required or configured.
- Dependency versions are constrained by major/minor ranges and resolved in
  `uv.lock`; future upgrades require rerunning the validation suite.
