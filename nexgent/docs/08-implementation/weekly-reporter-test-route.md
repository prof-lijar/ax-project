# Weekly Reporter Test Route

Date: 2026-08-13

## Summary

The frontend now provides a dedicated `/test-agent` workbench for manually
running and inspecting the `ansimk_weekly_reporter` LangGraph workflow. The
page uses the live Agent Server boundary; it does not substitute mock results
in the browser.

The workbench supports:

- a Monday-only reporting-week input and an IANA timezone selector;
- Agent Server availability feedback and retry;
- starting and cancelling a stateless weekly-report run;
- streamed batch, ward-data, per-ward, fallback, and completion progress;
- individual report selection and Korean Markdown rendering;
- current and prior danger-day totals with their delta;
- visible model-versus-template generation mode and batch warnings; and
- an expandable raw report payload for contract-level inspection.

## Architecture and Decisions

- `/test-agent` is a first-class app section. It participates in the existing
  History API routing, direct-load normalization, sidebar selection, and
  trailing-slash handling.
- `src/shared/api/agentServerClient.ts` remains the network boundary. The page
  does not call `fetch` directly.
- Weekly report requests use `POST /runs/stream` with
  `assistant_id: ansimk_weekly_reporter`, `stream_mode: [custom, values]`, and
  `on_disconnect: cancel`.
- An `AbortController` disconnects an active request. The Agent Server cancel
  policy ensures the graph run is cancelled as well as the browser stream.
- The client validates progress-event shapes and the final report, metric, and
  generation-mode fields before exposing the result to React. A completed
  stream without a valid final batch is reported as malformed.
- Report and progress contracts live in
  `src/shared/types/weeklyReport.ts`. They mirror the Python contracts without
  placing provider configuration or credentials in frontend state.
- Existing `ChatMarkdown` rendering is reused for the generated report. Raw
  HTML remains disabled, and links retain the existing safe external-link
  behavior.
- The date input defaults to the most recent completed local Monday.
  Non-Monday values cannot be submitted, matching `WeeklyReportRequest`
  validation.

## Operation

Start the Agent Server from `agents/`:

```bash
uv run langgraph dev --host 0.0.0.0 --port 2024
```

Start the frontend from `frontend/`:

```bash
npm run dev -- --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:5173/test-agent
```

For a non-default server, configure the same variable used by Chat:

```bash
VITE_AGENT_SERVER_BASE_URL=http://agent-host:2024 npm run dev -- --host 127.0.0.1
```

Choose a Monday, select the reporting timezone, and use **Run reporter**. The
workflow queries a bounded three-ward slice from
`ansimk.analysis_warddangerdaily` through the database MCP. When model
configuration is unavailable, reports still complete through the workflow's
template fallback and the workbench shows the warning and fallback mode.

## Validation

Completed from `frontend/`:

```bash
npm test
npm run build
CARGO_TARGET_DIR=/tmp/nexgent-cargo-check cargo check --manifest-path src-tauri/Cargo.toml
```

Results:

- all 34 Vitest assertions passed across seven test files;
- the TypeScript check and Vite production build passed; and
- the Tauri Rust check passed.

The new regression coverage verifies `/test-agent` route resolution, the exact
weekly-reporter request payload and cancel-on-disconnect setting, progress
delivery, final batch parsing, and rejection of an invalid completed payload.

## Known Limitations and Remaining Verification

- The frontend and health proxy returned HTTP 200, but the running Compose
  Agent Server image is stale and registers only `agent` and `chat`. Rebuild
  `agent-server` from the current agents workspace, then open
  `http://127.0.0.1:5173/test-agent`, run a Monday, confirm three selectable
  ward reports, and verify that cancelling a second run stops it.
- `npm audit --audit-level=moderate` could not reach the npm advisory endpoint
  in the sandbox. An elevated attempt was also denied because it would disclose
  project dependency metadata to the public registry. Run the following in an
  approved network environment:

  ```bash
  cd frontend
  npm audit --audit-level=moderate
  ```
- The workflow is a bounded ward-risk validation prototype. Business meaning,
  scheduling, authentication, persistence, and delivery are outside this
  frontend test route.
- Run history is not persisted. Starting a new run or reloading the app clears
  the displayed result.
