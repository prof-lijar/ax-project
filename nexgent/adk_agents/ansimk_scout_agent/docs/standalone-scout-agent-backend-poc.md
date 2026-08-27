# Standalone ansimk Scout Agent backend POC

Date: 2026-08-27

## Scope

This Phase 1 implementation is wholly contained in
`adk_agents/ansimk_scout_agent/`. It does not import or change Nexgent's
LangGraph agents, backend, frontend, shared model configuration, RAG workflows,
Compose stack, Scheduling Agent POC, or Slack behavior.

## Why native tool calling was removed

The initial live preflight reached the existing internal `gemma-4-31b`
OpenAI-compatible endpoint, but the server rejected ADK/LiteLLM function tools:

```text
"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser
tool_choice="required" requires --tool-call-parser
```

No shared server flags or configuration were changed, and no external model was
introduced. The revised Scout keeps Google ADK for both LLM stages but removes
all Agent tools:

```text
POST /v1/scout/runs
  -> ScoutRunService
  -> search_planning_agent (ADK/LiteLLM, tools=[], SearchPlan output schema)
  -> deterministic DDGS search
  -> deterministic rank-preserving selection
  -> deterministic HTTPX fetch + Trafilatura extraction
  -> ansimk_scout_agent summary stage (ADK/LiteLLM, tools=[])
  -> deterministic report/source validation
  -> report.md + execution.jsonl
```

The stages are independent Agents invoked in sequence by application code. They
are not an ADK parent/sub-agent hierarchy and do not delegate autonomously.

## Responsibilities

### Planning Agent

The planning Agent receives only topic and optional keywords. ADK
`output_schema=SearchPlan` requests JSON containing one to three concise
queries. Pydantic rejects empty plans, more than three queries, blank or
over-160-character queries, URLs, and extra fields before search begins.

### Deterministic application

For each plan, Python allocates the six-result total budget across all queries,
calls `DdgsSearchProvider`, merges normalized results, removes tracking
parameters and duplicates, preserves rank, and selects the first three URLs.
This simple strategy intentionally has no embeddings, reranker, or additional
LLM stage.

`WebFetcher` revalidates each initial and redirected URL against the public
HTTP(S) boundary, disables environment proxy inheritance, enforces a 12-second
HTTPX timeout and 1 MiB body limit, and accepts only HTML, XHTML, or plain text.
Trafilatura receives already-fetched HTML and extracts at most 12,000 characters.
There is no recursive crawling, JavaScript renderer, browser, PDF extraction,
authentication, or file download support.

### Summary Agent

The summary Agent receives only the original request and successful bounded
evidence blocks with source URLs. Its instruction treats page text as untrusted
data rather than instructions, prohibits unsupported facts, requires uncertainty
when evidence is insufficient, and permits only supplied evidence URLs in the
Sources section. It has no tools, filesystem access, Slack, or scheduling.

### Validation and persistence

Application code requires the exact ordered headings `# Scout Report`,
`## Topic`, `## Summary`, `## Key Findings`, and `## Sources`, with non-empty
content. Every URL anywhere in the report must be among the successfully fetched
URLs. The validated report is written atomically beneath a UUID-derived run
directory; user text never becomes a path.

Execution logs include `run_started`, planning start/completion, search
completion, one completion record per fetch attempt, summary start/completion,
`report_saved`, and `run_succeeded` or `run_failed`. Raw provider/model errors,
keys, endpoints, full prompts, full model responses, and raw page bodies are not
logged.

## FastAPI contract

The public contract is unchanged:

- `GET /health/live`
- `GET /health/ready`
- `POST /v1/scout/runs`

The POST remains synchronous and accepts `topic` plus optional `keywords`. A
success returns `run_id`, `status`, `report`, validated `sources`, and relative
report/log artifact references. Raw ADK runtime/session APIs remain private.

## Locked stack

| Purpose | Package | Locked version |
| --- | --- | --- |
| Agent runtime | `google-adk` | 2.8.0 |
| Internal model adapter | `litellm` | 1.98.0 |
| Search | `ddgs` | 9.16.0 |
| HTTP | `httpx` | 0.28.1 |
| Extraction | `trafilatura` | 2.2.0 |
| API | `fastapi` | 0.141.1 |
| Validation | `pydantic` | 2.13.4 |
| ASGI server | `uvicorn` | 0.52.4 |

## Automated verification

On 2026-08-27:

```text
uv lock --check          passed
ruff format --check      passed (22 files)
ruff check               passed
pytest                   passed (42 tests)
```

Tests cover SearchPlan acceptance/rejection and planning-output validation,
tool-free Agent registration, isolated LiteLLM settings, deterministic provider
calls, result-budget allocation, URL selection/deduplication, existing fetch
safety, successful-evidence isolation, report validation/persistence, observable
pipeline phases, safe planning/search/fetch/summary failures, and the unchanged
FastAPI contract. The only warning is ADK's upstream `BaseAgentConfig`
deprecation warning.

## One bounded live E2E verification

The single live request used:

```text
Topic: 고독사 예방 AI IoT 서비스 최근 동향
Keywords: 고독사 예방, AI 돌봄, IoT 모니터링
Model: gemma-4-31b through the existing internal OpenAI-compatible endpoint
```

Result: HTTP 200 success in 61.124 seconds. Run ID:
`1848dcbe644a4c11a3c857f21d9502dd`.

The planning Agent produced:

1. `고독사 예방 AI IoT 서비스 최신 동향 및 사례`
2. `AI 돌봄 서비스 및 IoT 모니터링 기술 트렌드`
3. `정부 및 지자체 고독사 예방 스마트 돌봄 시스템 현황`

DDGS returned six unique bounded results. Rank-preserving selection chose:

1. `https://koreascience.kr/article/JAKO202311643855609.pdf` — safely rejected
   as unsupported PDF content.
2. `https://whitejung0.tistory.com/entry/서울시는-왜-AI로-고독사를-막으려-할까｜2026-스마트-안부확인서비스-최신-정책-정리`
   — fetched and extracted, 4,308 characters.
3. `https://www.lucintel.com/ko/smart-baby-bassinet-market.aspx` — fetched and
   extracted to the 12,000-character cap, but unrelated and not cited.

The summary cited only the relevant Tistory URL. The persisted report exactly
matched the HTTP response, and the cited-source set was a subset of successful
fetches. The report's 서울시 smart-check-in findings align with the relevant
page's extracted evidence; the unrelated page was not used in the report.

Artifacts:

```text
var/runs/1848dcbe644a4c11a3c857f21d9502dd/report.md
var/runs/1848dcbe644a4c11a3c857f21d9502dd/execution.jsonl
```

Both artifact files have mode `0600`. Automated inspection found no API key,
model base URL, or complete raw page body in the JSONL log.

## Known limitations

- Native function/tool calling remains unsupported by the current shared model
  serving configuration. The working pipeline intentionally does not use it.
- DDGS is an unofficial public-search adapter and can return low-relevance or
  rate-limited results. The live run selected one unrelated result.
- URL selection is intentionally rank-only; it does not score authority or
  semantic relevance.
- The live report relied on one relevant blog source. The mechanical grounding
  and citation checks passed, but source authority and multi-source corroboration
  remain production-quality gaps.
- DNS is checked before HTTPX connects but the checked address is not pinned,
  so the mitigation is not complete DNS-rebinding protection.
- POST execution and ADK sessions are synchronous/in-memory. There is no queue,
  cancellation API, database, retention policy, or multiprocess coordination.
- Only static HTML/XHTML/plain text is extracted. Browser rendering, recursive
  crawling, PDF extraction, downloads, and authenticated pages remain absent.

## Deferred integrations

- Frontend: may integrate later against the unchanged POST response, but no
  frontend files were changed in this phase.
- Scheduling: should later invoke the same run-service or HTTP boundary; the
  Agents own no schedule state.
- Slack: should later run deterministically after successful persistence; the
  Agents own no notification credentials or tools.

