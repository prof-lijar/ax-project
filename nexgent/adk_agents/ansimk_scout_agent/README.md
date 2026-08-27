# ansimk_scout_agent

Standalone Phase 1 Google ADK backend POC for bounded web research. The public
FastAPI contract accepts a topic and optional keywords, produces a Markdown
report, and saves deterministic run artifacts.

## Architecture

The internal `gemma-4-31b` serving configuration rejects OpenAI-style native
tool choice because automatic tool choice and a tool-call parser are not enabled.
The Scout does not change or work around that shared server configuration.
Instead, it uses two independent tool-free ADK stages with deterministic Python
between them:

```text
topic + keywords
  -> search_planning_agent (ADK + LiteLLM, tools=[])
  -> validated SearchPlan with 1-3 queries
  -> Python DDGS search and rank-preserving URL selection
  -> Python HTTPX fetch and Trafilatura extraction
  -> ansimk_scout_agent summary stage (ADK + LiteLLM, tools=[])
  -> Markdown/source validation
  -> report.md + execution.jsonl
```

`ScoutRunService` owns this order explicitly. There is no parent/sub-agent
hierarchy, autonomous delegation, native function call, filesystem Agent tool,
or raw ADK runtime API exposed to clients.

## Configure and run

Python 3.11-3.13 and `uv` are required. From this directory:

```bash
cp .env.example .env
```

Set `OPENAI_API_BASE`, `OPENAI_API_KEY`, and `SCOUT_MODEL` in `.env`. Secrets
must not be committed. A bare model value is routed as `openai/<value>` through
ADK `LiteLlm`.

```bash
uv sync
uv run uvicorn app.fast_api_app:app --host 127.0.0.1 --port 8091
```

## API

```bash
curl -fsS http://127.0.0.1:8091/health/live
curl -fsS http://127.0.0.1:8091/health/ready
```

```bash
curl -fsS -X POST http://127.0.0.1:8091/v1/scout/runs \
  -H 'Content-Type: application/json' \
  -d '{"topic":"고독사 예방 AI IoT 서비스 최근 동향","keywords":["고독사 예방","AI 돌봄","IoT 모니터링"]}'
```

The success shape remains:

```json
{
  "run_id": "...",
  "status": "success",
  "report": "# Scout Report ...",
  "sources": ["https://..."],
  "report_artifact": "runs/<run-id>/report.md",
  "log_artifact": "runs/<run-id>/execution.jsonl"
}
```

## Bounds and trust boundary

- SearchPlan: 1-3 unique queries, 160 characters maximum, no URLs
- Search: six normalized results total, spread across plan queries
- Selection: first three unique eligible URLs in merged search rank order
- Fetch: HTTP(S) public addresses only; redirect destinations are revalidated
- Request timeout: 12 seconds; response limit: 1 MiB
- Extraction: HTML/XHTML/plain text only; 12,000 characters per page
- No PDFs, recursive crawling, JavaScript rendering, authentication, or downloads
- Evidence is untrusted data, never instructions
- Every report URL must be a successfully fetched URL

## Artifacts

```text
<SCOUT_OUTPUT_ROOT>/
  runs/
    <run-id>/
      report.md
      execution.jsonl
```

Logs expose planning/search/fetch/summary/persistence phases and safe metadata,
but exclude keys, model endpoints, full prompts, raw model responses, and raw
page bodies.

```bash
SCOUT_RUN_ID=0123456789abcdef0123456789abcdef
sed -n '1,240p' "var/runs/${SCOUT_RUN_ID}/report.md"
python -m json.tool --json-lines "var/runs/${SCOUT_RUN_ID}/execution.jsonl"
```

## Verify

```bash
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

The verified implementation and live smoke details are recorded in
[docs/standalone-scout-agent-backend-poc.md](docs/standalone-scout-agent-backend-poc.md).

## Deferred

- Nexgent frontend/backend integration
- scheduling and cron
- Slack notification
- durable queues, status polling, and retention management
- production search ranking or source-authority scoring

