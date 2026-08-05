# AX Agents Workspace

This is a greenfield Python environment for building production-oriented AX
agents with LangGraph. The workspace is split into focused packages for
contracts, runtime, graphs, tools, integrations, gateway, and evaluations.
The first graph remains provider-neutral so the runtime can be validated
without an LLM API key.

## Quick start

```bash
uv sync --dev
uv run pytest
uv run python -c 'from ax_agents import graph; print(graph.invoke({"message": "hello"}))'
uv run ruff check packages src tests
uv run langgraph dev --no-browser
```

The local server exposes API docs at <http://127.0.0.1:2024/docs>. Its
in-memory mode is for development and testing, not production persistence.
Read [the architecture specification](docs/ax-agents-architecture.md) before
changing any package or runtime boundary. See [the environment setup record](docs/langgraph-environment-setup.md)
for the local validation details.
