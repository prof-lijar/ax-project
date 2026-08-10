# AX Agents Workspace

This is a greenfield Python environment for building production-oriented AX
agents with LangGraph. The workspace is split into focused packages for
contracts, runtime, tools, integrations, persistence, observability, and
evaluations. Deployable services live under `apps/`; self-contained business
workflows live under `workflows/`.
The deterministic smoke graph remains provider-neutral so the runtime can be
validated without an LLM API key. A separate `chat` graph calls an
OpenAI-compatible model endpoint through the shared async integration adapter.

## Quick start

```bash
uv sync --dev
uv run pytest
uv run python -c 'from workflows.smoke import graph; print(graph.invoke({"message": "hello"}))'
uv run ruff check apps workflows packages tests
uv run uvicorn apps.gateway.main:app --port 8080
uv run langgraph dev --host 192.168.0.18 --port 2024 --no-browser
```

The LAN development server exposes API docs at
<http://192.168.0.18:2024/docs>. Its in-memory mode has no authentication and
is for development on a trusted network, not production use or persistence.
Read [the architecture specification](docs/ax-agents-architecture.md) before
changing any package or runtime boundary. See [the environment setup record](docs/langgraph-environment-setup.md)
for the local validation details and [the LLM integration guide](docs/llm-integration.md)
for configuring and invoking the `chat` graph.
