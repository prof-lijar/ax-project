# AnsimK Scout Agent Frontend POC

Date: 2026-08-28

## Scope

This implementation adds the standalone `ansimk_scout_agent` to the existing
Nexgent Agents experience. The Scout backend remains a host process outside
Docker. Existing LangGraph agents, the Nexgent backend, RAG, Weekly Reporter,
and shared model configuration remain unchanged.

The Scout appears as an agent card rather than a new top-level navigation
section. Its dedicated route is:

```text
/agents/ansimk_scout_agent
```

## Frontend architecture

The static agent catalog now includes an `AnsimK Scout Agent` record with a
`Google ADK` runtime label. `AgentDefinition.canRunInChat` explicitly separates
general Chat agents from agents with dedicated workbenches. Weekly Reporter and
RAG retain their existing Chat behavior; Scout is not offered in the Chat agent
selector and its catalog card has no Chat action.

The Scout route opens a dedicated workbench with:

- a required Topic field;
- optional comma- or newline-separated Keywords;
- a synchronous Run Scout action;
- an honest loading state with a frontend elapsed `MM:SS` timer and no
  estimated percentage or fabricated stages;
- Markdown report rendering using the existing `react-markdown` and
  `remark-gfm` dependencies;
- safely opened source links; and
- authoritative status, duration, Asia/Seoul completion time, and source count;
  and
- plain-text run ID, report artifact, and execution-log references.

A failed retry leaves the previous successful result visible while clearly
showing the safe timing and artifact metadata for the latest failed attempt in
a separate block.

## API contract

The focused browser client reads `VITE_SCOUT_API_BASE_URL`, removes trailing
slashes, and posts directly to the standalone host API:

```text
POST http://192.168.0.18:8091/v1/scout/runs
```

Without an explicit variable, browser execution follows the RAG convention and
uses the current page hostname with port 8091. Non-browser/test execution falls
back to `http://127.0.0.1:8091`.

Request:

```json
{
  "topic": "고독사 예방 AI IoT 서비스 최근 동향",
  "keywords": ["AI 돌봄", "IoT 모니터링", "고독사 예방"]
}
```

Successful responses are runtime-validated before rendering:

```json
{
  "run_id": "...",
  "status": "success",
  "started_at": "2026-08-28T01:30:00Z",
  "completed_at": "2026-08-28T01:31:17.896000Z",
  "duration_seconds": 77.896,
  "source_count": 1,
  "report": "# Scout Report\n...",
  "sources": ["https://..."],
  "report_artifact": "runs/.../report.md",
  "log_artifact": "runs/.../execution.jsonl"
}
```

The frontend validates timezone-aware timestamps, a nonnegative finite
duration, and `source_count === sources.length`. While the synchronous request
is active, a `Date.now()`-based timer updates once per second and is cleared on
completion or unmount. After success, the UI uses `duration_seconds` from the
backend instead of the frontend timer. Completion is converted explicitly to
`Asia/Seoul` and labelled `KST`.

Scout failures created after a run begins remain HTTP 502 and may include safe
terminal metadata:

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
    "log_artifact": "runs/.../execution.jsonl"
  }
}
```

The previous successful report is not replaced by this failure metadata.
Pre-run validation/readiness errors keep their existing 422/503 shapes.

Artifact values are references owned by the standalone Scout service. The POC
does not present them as downloadable URLs.

## Browser-to-host connectivity

Compose supplies this Vite environment value to the existing frontend service:

```dotenv
VITE_SCOUT_API_BASE_URL=http://192.168.0.18:8091
```

The Vite `/scout-api` proxy is no longer used. This avoids resolving
`127.0.0.1` inside the frontend container and matches the established RAG
deployment pattern:

```text
Nexgent browser UI :5173
  -> direct cross-origin POST to standalone Scout FastAPI :8091
  -> ScoutRunService
  -> ansimk_scout_agent
       -> web_search (DDGS)
       -> web_fetch_and_extract (HTTPX + Trafilatura)
  -> validated Markdown report and artifact references
```

Scout FastAPI uses explicit CORS for `http://192.168.0.18:5173`, permits only
POST for this browser boundary, does not allow credentials, and accepts only
the `Accept` and `Content-Type` request headers. Localhost frontend origins are
not enabled because the current deployed RAG pattern uses the exact LAN
frontend origin.

## Run and manually verify

Start the already-verified Scout backend:

```bash
cd ~/nextor_ai/ax-project/nexgent/adk_agents/ansimk_scout_agent
uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8091
```

The `0.0.0.0` bind makes the standalone process reachable through the host's
LAN address. It does not itself open the port through company or host firewall
policy.

Start the existing frontend in another terminal:

```bash
cd ~/nextor_ai/ax-project/nexgent/frontend
npm run dev
```

Open `http://192.168.0.18:5173/agents/ansimk_scout_agent`, enter a Topic and
optional Keywords, and select **Run Scout**. A successful run should render the
live elapsed timer followed by the Markdown report, fetched sources, status,
authoritative duration, KST completion time, source count, run ID, report
artifact reference, and execution-log reference.

## Authoritative timing update — 2026-08-28

`ScoutRunService` now captures timezone-aware UTC start/completion values and a
monotonic duration. The success API response and terminal `run_succeeded` JSONL
event use the exact same values. A safe application exception carries the
equivalent terminal metadata for HTTP 502 failures without exposing the raw
exception. This timing belongs to the Scout execution path and is suitable for
later scheduled runs without a browser-side duration calculation.

## Validation

The focused tests cover the catalog/card, dedicated route, Chat exclusion,
Topic validation, keyword parsing, loading guard, success rendering, safe error
state, direct configured API URL, resolver normalization, request contract,
HTTP errors, network errors, malformed responses, and exact-origin CORS.

Validation commands:

```bash
cd ~/nextor_ai/ax-project/nexgent/frontend
npm run test
npm run build
npm audit --audit-level=moderate
cargo check --manifest-path src-tauri/Cargo.toml
```

Automated verification on 2026-08-28, including the authoritative timing
update:

- Focused timing/client workbench tests: 2 files and 18 tests passed.
- `npm run test`: 20 test files and 164 tests passed.
- `npm run build`: TypeScript checking and the Vite production build passed.
- `npm audit --audit-level=moderate`: zero vulnerabilities reported.
- `cargo check --manifest-path src-tauri/Cargo.toml`: passed using an isolated
  temporary `CARGO_TARGET_DIR`. The repository's pre-existing shared target
  cache referenced a missing `workflow-helper` generated-permissions file, so
  the isolated check avoided modifying or cleaning that unrelated build state.
- Scout `uv lock --check`: passed.
- Scout `ruff format --check .` and `ruff check app tests`: passed.
- Scout `pytest`: 46 tests passed with two existing dependency warnings.
- `docker compose config -q`: passed without starting or restarting services.

The dependency audit result above was recorded earlier on the same date and no
dependency or lockfile changed in this connectivity update. A second audit
attempt was not permitted by the execution environment because it would send
the private dependency tree to the external npm registry.

A browser-based live Scout run was not repeated as part of the automated test
suite. Complete the manual verification above with both services running to
validate the company-network route and rendered live response together.

## Current limitations and follow-up

- The POST request is synchronous and may take 60–80 seconds or longer; there
  is no streamed phase progress or cancellation control in this POC.
- There is no frontend run history or artifact download endpoint.
- Port 8091 must be reachable from the user's browser. Company-network and
  firewall approval may be required and is outside this implementation.
- Scout has no durable systemd unit yet. Host process management remains an
  operational handoff TODO analogous to the existing RAG service.
- Scheduling/cron controls remain TODO and should connect only after a separate
  integration is approved. A future scheduler should reuse the same Scout run
  service/API path rather than create a second Scout implementation.
- Slack notification configuration and delivery remain TODO.
- Research quality, search ranking, crawling depth, and backend behavior were
  intentionally not changed by this frontend work.

## Additional research instructions update — 2026-08-31

The Scout workbench now includes one optional **Additional research
instructions** textarea below Keywords. The same value is used by Run Now and
Schedule Scout. Input is trimmed, blank content is omitted from outgoing JSON,
and normalized content is capped at 2,000 characters. The helper copy states
that the value cannot change Scout's source and safety rules.

Persisted schedule records expose the normalized value so the scheduled-job card
can reconstruct and display it after reload. Legacy records without the field
are accepted and rendered with a `null` value.

Validation on 2026-08-31:

- focused Scout workbench, direct client, scheduling client, and catalog tests:
  65 passed;
- full frontend suite: 21 files and 209 tests passed; and
- `npm run build`: TypeScript and Vite production build passed, with the existing
  advisory for a JavaScript chunk larger than 500 kB.
