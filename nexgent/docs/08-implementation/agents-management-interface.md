# Agents Management Interface

Date: 2026-08-13

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
