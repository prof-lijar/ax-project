# Weekly Reporter Frontend Workbench

Date: 2026-08-19

Update: 2026-08-20

Chat and live Weekly Reporter execution now use independent request lanes in
the shared Chat workspace. One chat stream and one report run may remain active
at the same time. Each lane owns its own abort controller, loading state, error
state, and Cancel action; cancelling or completing one does not mutate the
other. A lane still rejects a second request of its own type. This removes the
former frontend serialization while preserving bounded execution and
cancel-on-disconnect for both network requests.

The Agent Server development image now starts LangGraph with four concurrent
run slots. This is required because the installed in-memory development runtime
otherwise defaults to one active run and queues Chat behind the entire Weekly
Reporter graph. The interactive report request itself uses
`max_concurrency: 1`: report generation remains sequential inside that run so
the shared model endpoint is not pre-filled with four report requests before a
later Chat request arrives. This reserves scheduling opportunity, not GPU
capacity; a Chat request can still wait for the single model generation already
in progress.

The implementation introduces a small `RequestLanes` owner with separate
`chat` and `weekly-report` controllers. The Chat composer cancels only the chat
lane. A persistent background-run control cancels only Weekly Reporter. Chat
and report errors/notices are also separate, and normal chat does not create a
mock Weekly Reporter trace while the real reporter is active.

Validation completed on 2026-08-20:

- 97 frontend tests passed across 15 files, including three request-lane
  concurrency and cancellation regressions;
- the complete agent test suite passed with one environment-dependent test
  skipped, including the new development-server concurrency contract;
- full agent Ruff checks and `langgraph validate` passed with three registered
  graphs;
- root `docker compose config --quiet` passed;
- the TypeScript and Vite production build passed;
- Tauri `cargo check` passed using the isolated target directory
  `/tmp/nexgent-cargo-agent-concurrency`; and
- `npm audit --audit-level=moderate` reported zero vulnerabilities.

The full `docker compose up --build -d` deployment was attempted but could not
connect to `/var/run/docker.sock` from the current account. The rebuilt runtime
therefore remains an operator deployment step:

```bash
cd /home/nextor-ai-02/nextor_ai/ax-project/nexgent
sudo docker compose up --build -d
```

This guarantees independent client requests and concurrent Agent Server run
scheduling, but not constant chat latency if bulk generation saturates a shared
inference server. Production deployment should reserve interactive model
capacity or give bulk workers a separate OpenAI-compatible endpoint. Browser
end-to-end verification remains:

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

Start Weekly Reporter from Chat, submit a normal chat message before the report
finishes, and confirm both progress independently and each Cancel action affects
only its own request.

## Summary

The Weekly Reporter catalog route at `/agents/1` now renders the real
`ansimk_weekly_reporter` workbench. The earlier `/test-agent` route remains as
a test-oriented alias of the same component. Other `/agents/:id` routes retain
the generic catalog detail experience.

Runs are explicit: opening the route does not query the database or send ward
facts to a model. The operator chooses a completed Monday and timezone, then
chooses how many reports to generate from 1 through 25. The frontend sends that
validated value as `limit` through the Agent Server SSE boundary. The control
defaults to three. On completion, the first report is selected while every
other returned report remains available in the subscriber selector.

## User Experience

The workbench provides:

- a Monday-only week input and IANA timezone selector;
- a validated 1–25 report-count control, defaulting to three;
- Agent Server readiness, retry, active progress, elapsed time, and cancel;
- one selected subscriber report at a time, with the first selected by
  default;
- four compact deterministic indicators: source coverage, danger days,
  movement average, and unresolved dispatches;
- safe Korean Markdown rendering, generation-mode disclosure, and prompt/
  validation provenance; and
- separate empty-result, source-warning, fallback, and request-error states.

Raw report JSON is not exposed in the product view. This reduces accidental
display of unnecessary care-related metadata while preserving the useful
deterministic indicators and rendered summary.

## Runtime Path

```text
/agents/1
  -> shared Agent Server client
  -> POST /runs/stream (assistant_id: ansimk_weekly_reporter, selected limit)
     with max_concurrency: 1 (interactive capacity reservation)
  -> private weekly-report FastAPI source
  -> read-only ansimk PostgreSQL queries
  -> deterministic metrics
  -> validated Korean narrative or disclosed deterministic fallback
  -> up to the selected number of ordered reports
  -> first report selected in the workbench
```

The root `compose.yaml` now includes `weekly-report-api`, loads its database
settings from `agents/.env`, and makes Agent Server wait for the source API's
database-backed readiness check. The source service is private to the Compose
network and exposes no browser endpoint.

## Contracts and Security

- `src/shared/api/agentServerClient.ts` is the only frontend network boundary.
- The browser request uses `stream_mode: [custom, values]` and
  `stream_subgraphs: true` so per-ward progress is visible, plus
  `on_disconnect: cancel`.
- Namespaced `custom|...` events are parsed only as progress. Final report
  validation remains restricted to the top-level `values` event.
- The frontend contract mirrors the current and prior weekly metric snapshots,
  deltas, narrative, generation metadata, skipped wards, cursor, and warnings.
- Runtime parsing rejects malformed report, metric, narrative, and generation
  fields before React receives them.
- Database credentials and model configuration remain server-side.
- The page does not auto-run, persist reports, or deliver them to Slack.

## Operation

Configure `ANSIMK_DATABASE_DSN` in `agents/.env`, then run from the repository
root:

```bash
docker compose up --build -d weekly-report-api agent-server backend frontend
```

Open:

```text
http://192.168.0.18:5173/agents/1
```

Choose a completed Monday, enter a report count from 1 through 25, and click
**Generate N reports**. When enough eligible subscribers exist, confirm the
requested number of subscriber choices appears and that the first report is
already visible.

## Validation

The implementation is covered by route, selection, SSE payload, progress, and
contract parsing tests. Validation commands are:

```bash
cd frontend
npm test
npm run build
CARGO_TARGET_DIR=/tmp/nexgent-cargo-weekly-workbench \
  cargo check --manifest-path src-tauri/Cargo.toml

cd ..
docker compose config --quiet
```

Validation on 2026-08-19 completed with:

- 72 frontend tests passing across 12 files;
- a successful TypeScript and Vite production build;
- a successful Tauri `cargo check`;
- zero vulnerabilities from `npm audit --audit-level=moderate`;
- 16 focused weekly source/repository/graph tests passing;
- valid root and agents-only Compose configurations; and
- a read-only live source check returning three ordered items for the then-
  default count, with no skipped wards and a continuation cursor.

The existing frontend and Agent Server health endpoints return HTTP 200 and
the running Agent Server registers `ansimk_weekly_reporter`. That container
predates this integration and still requires the documented Compose rebuild.
The final model-backed batch run was not executed because ward-derived
qualitative facts require explicit approval for the configured LLM endpoint.

## Known Limits

- The workbench keeps only the current in-memory batch; reload clears it.
- Report scheduling, persistence, approval, and Slack delivery are separate
  workflows and are not triggered by this screen.
- A batch may contain fewer reports than requested when the source has fewer
  eligible subscribers or skips requested data; the UI presents an explicit
  no-result state rather than fabricating reports.
- The currently running root-owned Compose stack cannot be rebuilt by the
  unprivileged development user. An authorized operator must run the Compose
  command above before browser end-to-end verification.
