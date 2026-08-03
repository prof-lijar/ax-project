# Frontend Architecture

## Recommended Stack

- Desktop shell: Tauri 2.
- Frontend: TypeScript with React.
- Data fetching/cache: TanStack Query.
- Ephemeral UI state: Zustand.
- Styling: CSS modules with design tokens in plain CSS.
- Persistence: SQLite through the Tauri backend.
- Background work: Rust-managed services exposed through Tauri commands and events.

React is the default because it keeps hiring, component libraries, testing, and Tauri examples straightforward. Avoid introducing a second styling system unless a concrete component requirement justifies it.

## Process Model

AX Project should be split into three conceptual layers:

- Webview UI: renders screens, handles local interaction, dispatches commands.
- Tauri backend: owns persistence, agent process supervision, native integration, and event streaming.
- Agent runtime adapters: connect to mock agents, local processes, remote APIs, or future orchestration services.

The webview should not start or supervise agents directly.

## Frontend Module Layout

Recommended future app structure:

```text
src/
  app/
    App.tsx
    routes.tsx
    shell/
  features/
    agents/
    approvals/
    tasks/
    activity/
    mission-control/
  shared/
    api/
    components/
    state/
    time/
    types/
  styles/
src-tauri/
  src/
    commands/
    db/
    agents/
    events/
    policies/
```

## Tauri Command Boundary

Commands should expose product operations, not database tables.

Initial command groups:

- `workspace.get`
- `workspace.update_settings`
- `tasks.create`
- `tasks.update`
- `tasks.assign`
- `tasks.cancel`
- `tasks.list`
- `tasks.get`
- `approvals.list`
- `approvals.get`
- `approvals.decide`
- `approvals.request_more_evidence`
- `agents.list`
- `agents.get`
- `agents.pause`
- `agents.resume`
- `activity.list`
- `system.health`

Backend events:

- `workspace.updated`
- `task.created`
- `task.updated`
- `task.assigned`
- `approval.requested`
- `approval.decided`
- `agent.heartbeat`
- `agent.availability_changed`
- `agent.health_changed`
- `activity.appended`
- `system.warning`

## State Strategy

Use three kinds of state:

- Persistent domain state: stored in SQLite and read through commands.
- Live domain updates: streamed through Tauri events and merged into cached query results.
- Ephemeral UI state: selected row, collapsed rail, filters, sort order, drawer state.

Do not store critical workflow decisions only in frontend state.

## Responsiveness

The UI must stay responsive while agents run continuously:

- Long operations run in backend async tasks.
- UI commands return quickly with accepted, queued, or failed status.
- Progress arrives as events.
- Tables virtualize if row counts grow.
- Event listeners reconcile updates by id and version.

## Security Boundaries

- The frontend cannot execute shell commands directly.
- File-system access is mediated by Tauri permissions and backend commands.
- Credentials are stored through OS keyring or encrypted local storage, not frontend local storage.
- Approval policies are enforced in the backend, even if the UI hides unavailable actions.

## Error Handling

Classify errors as:

- User-correctable: missing input, invalid task, expired approval.
- Agent-correctable: insufficient evidence, failed attempt, bad plan.
- System-correctable: offline runtime, database lock, failed adapter.
- Fatal: corrupted state, incompatible schema, permission failure.

Every failed backend command should return:

- Stable error code.
- Human-readable message.
- Optional recovery action.
- Correlation id.

## Test Strategy

Frontend:

- Component tests for approval decision controls and task status rendering.
- Route/screen tests for queues.
- State reconciliation tests for streamed events.

Backend:

- Unit tests for policy checks, assignment scoring, event append behavior.
- Integration tests for SQLite migrations and command handlers.
- Mock adapter tests for agent runtime behavior.

End-to-end:

- Create task.
- Assign agent.
- Generate approval request.
- Approve with constraint.
- Observe task timeline update.
