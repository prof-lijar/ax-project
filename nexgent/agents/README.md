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
uv run langgraph dev --host 192.168.0.18 --port 2024 --no-browser --n-jobs-per-worker 4
```

The LAN development server exposes API docs at
<http://192.168.0.18:2024/docs>. Its in-memory mode has no authentication and
is for development on a trusted network, not production use or persistence.
Read [the architecture specification](docs/ax-agents-architecture.md) before
changing any package or runtime boundary. See [the environment setup record](docs/langgraph-environment-setup.md)
for the local validation details and [the LLM integration guide](docs/llm-integration.md)
for configuring and invoking the `chat` graph.
See [the web research tool guide](docs/web-research-tools.md) for creating the
reusable provider-neutral `web_search` and `web_fetch` tools. They are not wired
into the current chat graph.
See [the MCP integration guide](docs/mcp-integrations.md) for registering remote
Streamable HTTP MCPs, inspecting tools, managing environment-backed headers,
and exposing explicitly allowlisted MCP tools to workflows.
See [the weekly reporter implementation](docs/ansimk-weekly-reporter-implementation.md)
for the private FastAPI source, read-only Ansimk database settings, deterministic
metrics, and grounded Korean narrative contract.
See [the outbound Slack guide](docs/slack-outbound-messaging.md) for creating the
Slack app, configuring approved channels, sending a smoke message, and manually
delivering a human-approved weekly report.

## Docker development server

The root development container runs that same license-free `langgraph dev`
command automatically with four graph-run slots so Chat can run while an
interactive Weekly Reporter graph is active. Copy `.env.example` to the ignored
`.env`, set `OPENAI_API_KEY`, then start the complete Nexgent stack from the
parent `nexgent/` directory:

```bash
cd ..
docker compose up --build -d
docker compose logs -f agent-server
```

The local `agents/compose.yaml` starts the Agent Server and its private weekly
report source service, durable bulk-job database, worker, and private bulk
control API. Its weekly cron scheduler is opt-in through the `scheduled`
profile; the production stack (`../compose.prod.yaml`) owns the automatic schedule
by default. The
scheduler submits the previous completed week every Monday at 01:00
`Asia/Seoul`, and its week-derived idempotency key makes bounded delivery
retries safe. Set the weekly-report PostgreSQL connection from `.env.example`
before using that workflow. In the parent stack, open `/agents/1` to submit and
monitor up to 10,000 reports manually; bulk source paging remains capped at one
hundred wards per request.

Docker publishes the service only on `192.168.0.18:2024`. Inside the container,
LangGraph binds `0.0.0.0:2024` because the host's LAN address does not exist in
the container network namespace.

Stop it with:

```bash
docker compose down
```

See [weekly report terminal commands](apps/workers/README.md#generate-weekly-reports-and-save-to-the-database) for database-saving generation, 100-report tests, status checks, and continuation beyond 10,000 reports.

For ZIP-only reports for specific wards, enter comma-separated IDs such as `23, 45, 56` in the optional **Ward IDs** field at `/agents/1`, then choose **Run Agent**. See [selected-ward test runs](../docs/08-implementation/weekly-reporter-selected-ward-tests.md) for the 25-ID limit and rollout steps.
