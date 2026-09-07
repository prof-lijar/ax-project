# Agents Management Interface

Date: 2026-08-13

## Update: Weekly Reporter Is Bulk-Only

Date: 2026-09-04

Weekly Reporter still has its dedicated `/agents/1` workbench, but that page
now exposes only durable bulk generation. The catalog marks it as
non-Chat-capable and no longer shows fabricated preview runs. Quick Preview,
the Chat-triggered reporter execution, and the Test agent sidebar entry were
removed. `/test-agent` remains only as a compatibility redirect to
`/agents/1`. The dated sections below document earlier behavior and are
superseded where they describe interactive frontend execution.

## Update: Live Weekly Reporter Detail Workbench

Date: 2026-08-19

Weekly Reporter at `/agents/1` now intentionally uses its live batch-report
workbench instead of the generic mock-run detail surface. This supersedes the
2026-08-14 route-separation decision below. Other `/agents/:id` pages remain
unchanged. Opening the route is read-only; the operator must explicitly click
**Generate N reports** before the frontend invokes `ansimk_weekly_reporter`.

The route validates an operator-selected count from 1 through 25, sends it as
`limit`, renders streamed progress, selects the first ordered report by
default, and lets the operator switch among all returned subscriber summaries.
The count defaults to three and graph concurrency is capped at four. See
[Weekly Reporter Frontend Workbench](weekly-reporter-test-route.md) for the
runtime, security, UX, and validation details.

## Update: Catalog Detail and Test Workbench Route Separation

Date: 2026-08-14

All `/agents/:id` locations now render the dedicated catalog Agent Detail
page, including Weekly Reporter at `/agents/1`. The prior application-level
special case that rendered the test workbench for frontend agent ID `1` was
removed. The sidebar **Test agent** entry remains a distinct `/test-agent`
section and its page behavior was not changed.

Agent cards retain a real `/agents/:id` body link and also route clicks on the
remaining non-Chat card surface to the same detail location. The compact
**Chat** button stops event propagation, clears stale run intent, selects the
agent, and opens Chat without triggering the detail route or starting an
execution.

Validation completed from `frontend/`:

```bash
npm run test -- --run src/app/App.test.tsx src/shared/navigation/sections.test.ts src/features/agents/AgentsPage.test.tsx src/features/agents/AgentDetailPage.test.tsx
npm run build
cargo check --manifest-path src-tauri/Cargo.toml --target-dir /tmp/nexgent-cargo-chat-lifecycle
npm audit --audit-level=moderate
```

The focused routing and Agents suite passed 17 tests across four files, the
TypeScript/Vite production build completed successfully, the Tauri Rust check
passed, and the dependency audit reported zero vulnerabilities.

## Update: Request-aligned Mock Runs and Chat Errors

Date: 2026-08-14

The frontend mock stage timer now advances selected-agent runs only as far as
**Generating response**. It cannot mark a run completed. Successful mock
completion is owned by Chat after `agentServerClient.streamChat()` resolves,
while request failures and cancellations retain their existing failed and
cancelled terminal outcomes. The stream cancellation path also cancels its
associated mock run, including when navigation aborts an in-flight request.
Per-agent run isolation, run ID guards, and terminal-state protections remain
unchanged. Weekly Reporter's separate live SSE lifecycle was not modified.

The visible Chat error string now lives additively in the existing in-memory
Chat Zustand store alongside the transcript. Errors therefore remain visible
after navigating away from and back to Chat, and are cleared when a new
request begins. No browser-storage persistence was added, so a browser reload
or app restart still clears both session-only UI state and errors.

Validation completed from `frontend/`:

```bash
npm run test -- --run src/shared/state/useAgentRunStore.test.ts src/shared/state/useChatStore.test.ts
npm test
npm run build
cargo check --manifest-path src-tauri/Cargo.toml --target-dir /tmp/nexgent-cargo-chat-lifecycle
npm audit --audit-level=moderate
```

The focused store suite passed 9 tests across two files, the complete frontend
suite passed 54 tests across ten files, and the TypeScript/Vite production
build completed successfully. The Tauri Rust check passed using a clean
temporary target directory, and the dependency audit reported zero
vulnerabilities. Browser automation is not configured; the remaining manual
check is to begin a slow selected-agent response, confirm **Generating
response** remains active until streaming finishes, and verify that a request
error survives navigation away from and back to Chat.

## Update: Current and Latest Frontend Mock Runs

Date: 2026-08-14

Agent Detail now separates the active frontend mock lifecycle from the most
recent terminal mock result. **Current run** renders only a running record with
its prompt, existing four-stage progress, elapsed time, and frontend-only Stop
control. **Latest run** retains one completed, cancelled, or failed record per
agent with its prompt, duration, finished timestamp, final status, and a
contextual Chat action. No run-history array or paused/resumable state was
added.

The shared store keeps the existing `runsByAgentId` contract intact for Chat
and adds `latestRunsByAgentId` as a terminal snapshot map. Completing,
cancelling, or failing a mock run updates both maps atomically. Starting a new
run replaces the current slot for that agent without erasing its prior latest
terminal snapshot; other agents remain independent. Existing timers, run ID
guards, and terminal-state protections remain unchanged.

**Run again in Chat** and **Retry in Chat** reuse the existing selection-only
navigation path. They clear stale pending intent, select the agent, and open
Chat without resending the prior prompt, creating a run, or starting network
execution. Weekly Reporter's Chat-local live SSE lifecycle remains separate
and is neither stored nor controlled by these mock Current/Latest sections.

Validation completed from `frontend/`:

```bash
npm run test -- --run src/features/agents/AgentDetailPage.test.tsx src/shared/state/useAgentRunStore.test.ts
npm test
npm run build
```

The focused suite passed 12 tests across two files, the complete frontend
suite passed 52 tests across nine files, and the TypeScript/Vite production
build completed successfully. Browser automation is not configured; a manual
follow-up should confirm the compact Current/Latest layout and the contextual
navigation actions at wide and narrow desktop widths.

## Update: Selection-only Chat Entry

Date: 2026-08-14

The Agent Detail **Run in Chat** action and the Agents catalog **Chat** action
now clear any stale one-shot run intent, select the chosen agent, and navigate
to Chat. Chat opens with that agent visible in the existing selector and waits
for the user to type and send a message. Navigating from Agents no longer
creates the generated `Run Weekly Reporter for YYYY-MM-DD (Asia/Seoul).`
message or starts Weekly Reporter automatically.

The existing `requestAgentRun` state, Chat pending-run consumer,
`runWeeklyReport()` implementation, SSE lifecycle, request payloads, and
backend execution path remain unchanged. This update changes only the two
frontend Agents entry points and does not remove the one-shot infrastructure.

Validation completed from `frontend/`:

```bash
npm run test -- --run src/features/agents/AgentsPage.test.tsx src/features/agents/AgentDetailPage.test.tsx src/shared/state/useUiStore.test.ts src/shared/state/useAgentRunStore.test.ts
npm test
npm run build
```

The focused suite passed 15 tests across four files, the complete frontend
suite passed 49 tests across nine files, and the TypeScript/Vite production
build completed successfully. Browser automation is not configured, so the
remaining manual check is to open both Agents entry points and confirm Chat
shows the chosen agent without adding or starting a Weekly Reporter run.

## Update: Simplified Detail and Shared Mock Runs

Date: 2026-08-14

Agent Detail is now a compact execution-control view. Its rendered content is
limited to the agent identity, observation/readiness badges, **Run in Chat**
action, description, and a **Current run** section. Graph/runtime metadata,
capabilities, contract, configuration, limitations, and sample run history
remain in the frontend catalog contract but are no longer rendered on this
page. The readiness badge and Chat action share one right-side column and
stack responsively below the identity at narrow widths.

The Agents catalog keeps card-body detail navigation while shortening its
secondary action to **Chat** and its history count to **N runs**. The catalog
uses three fluid columns at wide widths, two at medium widths, and one at
narrow widths without changing route or selection behavior.

`src/shared/state/useAgentRunStore.ts` owns frontend-only simulated agent run
state keyed by frontend agent ID. Starting a selected-agent Chat message
replaces only that agent's prior mock run; other agents continue independently.
The store owns the existing four-stage simulated timer, triggering prompt,
timestamps, duration, and running/completed/cancelled/failed terminal state.
Chat and Agent Detail subscribe to the same records. Agent Detail's **Stop**
action clears only that mock timer and preserves a cancelled state; it does not
call Chat cancellation, abort an HTTP request, or invoke a backend endpoint.
Late completion and failure updates cannot overwrite a cancelled terminal run.

The live Weekly Reporter path remains separate and Chat-local. Its
`runWeeklyReport()` request, SSE progress events, payload, AbortController, and
existing Chat cancellation behavior were not moved into or consumed by the
mock store. Consequently, Agent Detail's Current run section represents only
the frontend mock lifecycle and does not claim to monitor or cancel a live
Weekly Reporter execution. Normal AX Chat without a selected agent creates no
agent run.

Validation completed from `frontend/`:

```bash
npm run test -- --run src/features/agents/AgentsPage.test.tsx src/features/agents/AgentDetailPage.test.tsx src/shared/state/useAgentRunStore.test.ts
npm test
npm run build
CARGO_TARGET_DIR=/tmp/nexgent-cargo-check-agent-runs cargo check --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
```

The focused suite passed 13 tests across three files, the complete frontend
suite passed 44 tests across nine files, the TypeScript/Vite production build
passed, the Rust check passed with a fresh temporary target, and the dependency
audit reported zero vulnerabilities. The repository's default Cargo target
still contains stale generated paths from the former `workflow-helper`
location, so the first default-target check failed before the clean temporary
target succeeded. Browser automation is not configured; responsive layout and
cross-route progress should still receive a manual browser check.

## Update: Weekly Reporter Runs in Chat

Date: 2026-08-14

Weekly Reporter is now the first live-data catalog entry. Clicking **Run in
Chat** on either its `/agents` card or `/agents/1` detail page selects the
agent, records a one-shot run request, and navigates to `/chat`. Chat consumes
that request once and immediately calls `ansimk_weekly_reporter`; it no longer
stops after changing the selected-agent label.

The run uses the most recent completed local Monday and `Asia/Seoul`. It sends
`POST /runs/stream` with `stream_mode: [custom, values]` and
`on_disconnect: cancel` through the shared Agent Server client. Live workflow
events advance the visible data-load/report-generation trace. On completion,
all ward Markdown reports and batch warnings are rendered in the transcript.
Cancellation uses the existing Chat stop control.

The frontend weekly contract now mirrors the ward-risk prototype:

- numeric `ward_id` and ward display name;
- current and previous `danger_days` plus their delta;
- `risk_data_loaded`, `ward_report_ready`, and fallback progress events; and
- ordered per-ward Markdown reports with batch warnings.

The UI holds only the transient run intent and transcript. MCP endpoint and
authorization configuration remain server-side. Other preview agents show a
clear no-live-runner error if invoked; no generic execution authority was
added.

Validation from `frontend/` passed with 34 tests across seven files and a
successful TypeScript/Vite production build. The live frontend and health
proxy both returned HTTP 200. Runtime execution exposed a stale deployed
Agent Server image on port 2024 that registers only `agent` and `chat`; the
Compose `agent-server` must be rebuilt from the current `agents/langgraph.json`
before browser end-to-end validation can pass.

## Update: Dedicated Agent Detail Routes

Date: 2026-08-14

The Agents workspace now separates catalog scanning from detailed inspection.
`/agents` remains the compact card grid, while `/agents/:id` renders the
selected catalog record as a dedicated detail page. The detail view preserves
the former inspector information: identity, readiness, description, graph ID,
runtime, last observation, capabilities, input/output contract, configuration,
limitations, and recent sample runs.

Each card body links directly to its detail route. A separate `Run in Chat`
button is available on both the card and detail page. Weekly Reporter uses the
live one-shot behavior described above; other records remain previews. The
card action is a sibling of the detail link and stops event propagation
defensively, so it cannot open the detail route.

The six preview catalog records now use sequential frontend IDs:

| ID | Agent | Graph ID |
| --- | --- | --- |
| `1` | Weekly Reporter | `ansimk_weekly_reporter` |
| `2` | Data Analyst | `preview_data_analyst` |
| `3` | Report QA | `preview_report_qa` |
| `4` | Document Assistant | `preview_document_assistant` |
| `5` | Database Assistant | `preview_database_assistant` |
| `6` | Risk Monitoring Agent | `preview_risk_monitoring_agent` |

These IDs are route and frontend catalog identifiers only; runtime calls use
the graph ID. The detail page reads the existing TanStack Query catalog and
does not duplicate agent metadata.

The History API/Zustand navigation layer now stores the active path as well as
the active section. This lets `/agents` and `/agents/:id` render different
views while keeping the Agents sidebar item active, and keeps direct loads and
browser Back/Forward navigation synchronized. Unknown catalog IDs render an
operational not-found state with a route back to the list.

Validation completed from `frontend/`:

```bash
npm test -- src/features/agents/AgentsPage.test.tsx src/features/agents/AgentDetailPage.test.tsx src/shared/navigation/sections.test.ts src/shared/api/agentCatalogClient.test.ts
npm run build
CARGO_TARGET_DIR=/tmp/nexgent-cargo-check.AytMsV cargo check --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
```

All 13 focused tests passed. The TypeScript check and Vite production build
also passed. Cargo check passed with a fresh temporary target directory; the
repository's existing default target cache contains stale generated paths from
the former `workflow-helper` location and was left untouched. The dependency
audit reported zero vulnerabilities. No browser automation dependency is
configured, so the remaining manual verification is:

```bash
npm run dev -- --host 127.0.0.1
```

Open `/agents`, follow each card to `/agents/1` through `/agents/6`, exercise
Back/Forward, and confirm that both `Run in Chat` actions open Chat with the
chosen agent displayed in the existing dropdown without first opening the
detail page from the card action.

## Summary

The placeholder Co-workers surface was replaced with a read-only Agents
workspace at `/agents`. The page is designed for monitoring and inspection of
LangGraph workflows without implying that runtime management is connected.

The initial catalog contains one preview of the existing Weekly Reporter graph,
`ansimk_weekly_reporter`. Its status and recent runs are visibly labeled as
sample data. The agent workflow itself was not changed.

## Implemented

- Renamed the left-navigation item from Co-workers to Agents and made `/agents`
  its canonical route.
- Kept `/co-workers` as a compatibility route that redirects to `/agents`,
  including paths with a trailing slash.
- Added a responsive agent catalog and inspector layout. The inspector presents
  the selected agent's purpose, graph identity, capabilities, input/output
  contract, configuration, known limitations, and recent sample runs.
- Added loading, unavailable, no-agent, filtered-empty, no-selection, and empty
  run-history states.
- Added search across agent identity, role, description, graph ID, current work,
  and capabilities.
- Added normalized readiness and run-status presentation with semantic badges.
- Omitted run, pause, resume, schedule, and configuration mutations because the
  corresponding authenticated runtime operations do not exist yet.

## Architecture and Data Decisions

`src/shared/types/agents.ts` defines frontend-normalized agent definition and
run summary contracts. `src/shared/api/agentCatalogClient.ts` owns the initial
Weekly Reporter fixture and normalizes external status strings to safe frontend
states. TanStack Query exposes that adapter to the feature page, so UI
components do not import mock records directly.

This catalog is separate from the legacy command-backed co-worker records used
by other sample workflow screens. Those fictional records no longer populate
the Agents page. Later integration can replace the catalog adapter with gateway
or Agent Server data without changing the page's component contract.

Weekly Reporter preview metadata follows its current workflow contract:

- Graph ID: `ansimk_weekly_reporter`
- Trigger: manual
- Required input: a Monday `week_start` in `YYYY-MM-DD` form
- Optional input: `timezone`, defaulting to `Asia/Seoul`
- Output: one Korean Markdown report per person plus batch warnings
- Current limitations: mock activity input, no scheduling, delivery,
  authentication, or persistent run history

No credentials, provider configuration, or agent output are stored in browser
state by this feature.

## Operation

Run the frontend from `frontend/`:

```bash
npm run dev -- --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:5173/agents
```

The legacy path can be checked at:

```text
http://127.0.0.1:5173/co-workers
```

## Validation

Completed from `frontend/`:

```bash
npm test
npm run build
CARGO_TARGET_DIR=/tmp/nexgent-cargo-check cargo check --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
```

All 26 tests passed. New coverage verifies deterministic Weekly Reporter
preview data, safe status normalization, catalog search, status presentation,
preview labeling, empty run history, filtered-empty behavior, the canonical
Agents route, and the legacy route redirect. The production TypeScript/Vite
build and Rust check passed. The dependency audit reported zero vulnerabilities.
Direct HTTP requests to `/agents` and `/co-workers` on the already-running Vite
development server both returned status `200`.

## Known Limitations and Follow-up

- The catalog, readiness, observation time, and run history are preview data;
  the page does not query Agent Server for live workflow or run state.
- Search uses the existing workspace-wide search field and remains ephemeral.
- UI selection and responsive layout have automated rendering and logic
  coverage, but no browser automation dependency is configured. Complete the
  remaining visual check with:

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

Then open `/agents`, select Weekly Reporter, search for `weekly` and a
nonmatching value, resize below 1040 px and 760 px, and confirm that
`/co-workers` is replaced with `/agents` while preserving the selected sidebar
section.

- The first live integration should replace the catalog adapter, add
  authenticated read-only discovery and run monitoring, and distinguish live
  observations from previews. Run controls, scheduling, persistence, and
  delivery require explicit backend contracts before UI controls are added.
