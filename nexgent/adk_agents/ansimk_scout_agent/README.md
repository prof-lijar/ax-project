# ansimk_scout_agent

Standalone Google ADK backend POC for bounded public-web research. The public
FastAPI contract accepts a topic, optional keywords, and optional subordinate
research guidance, produces a grounded Markdown report, and saves deterministic
run artifacts.

## Current architecture

```text
User / FastAPI
      |
      v
ScoutRunService
      |
      v
ansimk_scout_agent (one Google ADK Agent through LiteLLM)
      |
      +---- web_search Function Tool
      |       -> DDGS
      |
      +---- web_fetch_and_extract Function Tool
              -> HTTPX
              -> Trafilatura
      |
      v
Final Markdown
      |
      v
Deterministic validation and persistence
      +---- report.md
      +---- execution.jsonl
```

The Agent formulates queries, searches, chooses searched URLs to fetch, inspects
bounded extracted evidence, and writes the final report. Per-run Python tools
enforce network safety, URL eligibility, deduplication, and budgets regardless
of model behavior. `ScoutRunService` owns validation and persistence; neither is
an Agent tool.

The Nexgent frontend uses the same standalone browser-to-host connectivity
pattern as RAG:

```text
Browser /agents/ansimk_scout_agent
  -> http://192.168.0.18:8091/v1/scout/runs
  -> this standalone FastAPI application
  -> ansimk_scout_agent
```

FastAPI permits cross-origin POST requests only from the deployed Nexgent
frontend origin `http://192.168.0.18:5173`. The Scout process remains outside
Docker.

The previous tool-free `search_planning_agent` + `SearchPlan` + summary-Agent
pipeline was a temporary workaround while native tool calling was unavailable.
The internal `gemma-4-31b` endpoint has since been verified to support ADK/LiteLLM
function calls, so that workaround is historical and not part of the current
runtime path.

## Configure and run

Python 3.11-3.13 and `uv` are required. From this directory:

```bash
cp .env.example .env
```

Set `OPENAI_API_BASE`, `OPENAI_API_KEY`, and `SCOUT_MODEL` in `.env`. Never commit
secrets. A bare model value is routed as `openai/<value>` through ADK `LiteLlm`.

```bash
uv sync
uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8091
```

Binding to `0.0.0.0` is required for browsers on another machine to reach the
host service. Port 8091 exposure is an operational/network decision; this POC
does not modify firewall rules. The validated host deployment is supervised by
`nexgent-scout.service`; see
[docs/scout-systemd-supervision.md](docs/scout-systemd-supervision.md) for its
host-only environment strategy and operational commands.

## API

```bash
curl -fsS http://127.0.0.1:8091/health/live
curl -fsS http://127.0.0.1:8091/health/ready
```

```bash
curl -fsS -X POST http://127.0.0.1:8091/v1/scout/runs \
  -H 'Content-Type: application/json' \
  -d '{"topic":"고독사 예방 AI IoT 서비스 최근 동향","keywords":["고독사 예방","AI 돌봄","IoT 모니터링"],"additional_instructions":"Focus on public-sector deployment cases."}'
```

`additional_instructions` is optional, trimmed, normalized to absent when blank,
and limited to 2,000 characters. It is sent as subordinate user research
guidance and cannot replace the fixed Scout instruction, tool boundaries,
source-grounding rules, report contract, or host validation.

The success shape remains:

```json
{
  "run_id": "...",
  "status": "success",
  "started_at": "2026-08-28T01:30:00Z",
  "completed_at": "2026-08-28T01:31:17.896000Z",
  "duration_seconds": 77.896,
  "source_count": 1,
  "report": "# Scout Report ...",
  "sources": ["https://..."],
  "report_artifact": "runs/<run-id>/report.md",
  "log_artifact": "runs/<run-id>/execution.jsonl"
}
```

`started_at` and `completed_at` are timezone-aware UTC values captured by
`ScoutRunService`. `duration_seconds` is measured with a monotonic clock, and
`source_count` must equal the validated `sources` length. The terminal
`run_succeeded` JSONL event contains these exact same authoritative values.

Once a run exists, a safe failed response remains HTTP 502 and includes only
terminal metadata that can be shown to the user:

```json
{
  "detail": "Scout run failed.",
  "run": {
    "run_id": "...",
    "status": "failed",
    "started_at": "...",
    "completed_at": "...",
    "duration_seconds": 12.341,
    "source_count": 0,
    "log_artifact": "runs/<run-id>/execution.jsonl"
  }
}
```

Internal exception details are not exposed. Validation and readiness failures
that occur before a run exists retain their existing 422/503 response shapes.

## Bounds and trust boundary

- Agent/model turns: at most eight LLM calls
- Search: at most three calls and six normalized unique results total
- Fetch: at most three attempts, limited to URLs returned by this run's search
- Fetch: public HTTP(S) addresses only; every redirect is revalidated
- HTTPX timeout: 12 seconds; response limit: 1 MiB
- Extraction: HTML/XHTML/plain text only; 12,000 characters per page
- No PDFs, recursive crawling, JavaScript rendering, authentication, or downloads
- Page text is untrusted evidence, never instructions
- Every report URL must be a successfully fetched URL
- No filesystem, shell, Slack, or scheduling tools

## Artifacts and events

```text
<SCOUT_OUTPUT_ROOT>/
  runs/
    <run-id>/
      report.md
      execution.jsonl
```

The report is written atomically. JSONL events include `run_started`,
`agent_started`, per-call search/fetch start and completion, `agent_completed`,
`report_saved`, and `run_succeeded` or `run_failed`. Terminal events contain
the authoritative UTC start/completion timestamps, monotonic duration, and
source count returned by the API. Logs exclude keys, model endpoints, prompts,
model responses, and page bodies.

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

Backend implementation details are recorded in
[docs/standalone-scout-agent-backend-poc.md](docs/standalone-scout-agent-backend-poc.md).
The frontend Run Now flow, one-time Scheduling API integration, and persisted
schedule audit behavior are documented in
[docs/scout-scheduling-integration.md](docs/scout-scheduling-integration.md).

## Deferred

- recurring/cron scheduling and schedule update/reschedule
- Slack notification
- durable Scout run queues, Run Now status polling, and retention management
- production search ranking or source-authority scoring
