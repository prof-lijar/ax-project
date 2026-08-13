# Agents Management Interface

Date: 2026-08-13

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
