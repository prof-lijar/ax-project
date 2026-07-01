# Implementation Roadmap

## Phase 0: Project Setup

Outcome: runnable Tauri desktop skeleton.

Tasks:

- Create Tauri app scaffold.
- Choose frontend framework.
- Add routing and app shell.
- Add baseline styling system.
- Add SQLite setup and migration runner.
- Add typed command client between frontend and Tauri backend.
- Add mock data seed command.

Exit criteria:

- App launches on Linux.
- Navigation shell works.
- Backend command round trip works.
- Local database initializes.

## Phase 1: Static Operations Console

Outcome: product-shaped UI with mock data.

Tasks:

- Build Command Center.
- Build Tasks list and task detail.
- Build Approval queue and approval detail.
- Build Agents list and agent detail.
- Build Activity timeline.
- Implement filtering, sorting, and selection state.

Exit criteria:

- User can inspect mock tasks, agents, approvals, and events.
- Layout works at common desktop window sizes.
- Empty, loading, and error states exist.

## Phase 2: Local Domain Backend

Outcome: persistent local workflows.

Tasks:

- Implement task tables and commands.
- Implement agent registry tables and commands.
- Implement approval tables and commands.
- Implement event append and activity queries.
- Add optimistic concurrency for approval decisions.
- Add projections for command center counts.

Exit criteria:

- Created tasks survive restart.
- Assignment changes emit events.
- Approval decisions update state and timeline.
- Activity view is backed by local events.

## Phase 3: Mock Agent Runtime

Outcome: full human-agent workflow without real external agents.

Tasks:

- Add mock runtime adapter.
- Simulate agent heartbeats.
- Simulate task acceptance, progress, approval requests, completion, and failure.
- Add pause and resume controls.
- Add approval gating policy.
- Stream runtime updates to frontend.

Exit criteria:

- User can create a task and assign it to a mock agent.
- Mock agent can request approval.
- Human decision changes task flow.
- Agent status changes appear live.

## Phase 4: First Real Agent Adapter

Outcome: one real integration behind the adapter boundary.

Tasks:

- Select first agent runtime.
- Implement adapter connect/start behavior.
- Map agent messages to task events and artifacts.
- Map proposed actions to approval requests.
- Add adapter health reporting.
- Add integration-specific logging.

Exit criteria:

- One real agent can receive a task.
- Agent updates are visible in the app.
- Risky action proposals become approval requests.
- Adapter failure does not crash UI.

## Phase 5: Operational Hardening

Outcome: app can run continuously with recoverable state.

Tasks:

- Add background service supervision.
- Add stale work detection.
- Add desktop notifications.
- Add event deduplication.
- Add database backup/export.
- Add diagnostics view.
- Add end-to-end tests for core workflow.

Exit criteria:

- App tolerates restart during pending approvals.
- Agent offline state is detected.
- Duplicate runtime events do not corrupt timeline.
- Core workflow is covered by automated tests.

## Suggested First Milestone

Build a vertical slice:

1. Launch Tauri shell.
2. Show Command Center.
3. Create task.
4. Assign mock agent.
5. Mock agent requests approval.
6. Human approves with note.
7. Task timeline updates.
8. Mock agent completes task.

This validates the product model before investing in broad integration work.

## Team Responsibilities

Product/design:

- Validate workflows and terminology with target users.
- Define approval copy and risk language.
- Review dense desktop layouts at realistic window sizes.

Frontend:

- Build shell, screens, state reconciliation, and interaction details.
- Keep command client typed and stable.

Backend:

- Own SQLite schema, command handlers, policies, runtime adapters, and event stream.

Agent integration:

- Define adapter contracts.
- Convert runtime output into domain events, artifacts, and approvals.

QA:

- Verify state recovery, approval correctness, and live update behavior.

## Risks

- Chat interface gravity: the product could become a chat wrapper instead of an operations console.
- Approval fatigue: too many low-value approval requests can train users to approve blindly.
- Weak audit model: missing event detail will make agent behavior hard to trust.
- Adapter leakage: UI will become brittle if it depends on provider-specific runtime details.
- Background complexity: always-on agents require careful lifecycle supervision.

## Open Questions

- Which frontend framework will the team use?
- Which real agent runtime should be integrated first?
- Will the first version manage one local workspace or multiple workspaces?
- What actions are considered destructive in the initial policy?
- Should agents run only while the app is open, or through a background daemon?

