# Data Model

## Persistence Stance

Use SQLite locally. Store current workflow state in normalized tables and append immutable events for audit. This keeps the first desktop app simple while preserving a future path to sync.

Mission is a UX projection in the first version, not a separate table. A mission view is composed from task, owner agent, approvals, artifacts, and events.

## Core Entities

### Workspace

```text
workspace
  id
  name
  root_uri
  settings_json
  created_at
  updated_at
```

### Actor

Actors can be humans, agents, or system services. Keeping actors explicit makes audit, delegation, and future sync cleaner.

```text
actor
  id
  workspace_id
  actor_type
  display_name
  external_ref
  created_at
  updated_at
```

### Task

```text
task
  id
  workspace_id
  title
  goal
  status
  priority
  risk_level
  owner_type
  owner_id
  created_by
  created_at
  updated_at
  due_at
  context_summary
  version
```

### Agent

```text
agent
  id
  workspace_id
  actor_id
  name
  role
  description
  availability_state
  health_state
  adapter_kind
  permission_profile_id
  workload_limit
  last_heartbeat_at
  created_at
  updated_at
```

### Capability

```text
capability
  id
  key
  label
  description
```

```text
agent_capability
  agent_id
  capability_id
  confidence
  enabled
```

### Approval

```text
approval
  id
  workspace_id
  task_id
  requesting_agent_id
  parent_approval_id
  status
  risk_level
  action_type
  action_summary
  action_payload_json
  scope_json
  evidence_json
  bundle_summary_json
  scoped_decision_kind
  policy_reason
  requested_at
  expires_at
  decided_by
  decided_at
  decision_note
  version
```

### Artifact

```text
artifact
  id
  workspace_id
  task_id
  agent_id
  kind
  title
  uri
  content_preview
  metadata_json
  created_at
```

### Event

```text
event
  id
  workspace_id
  occurred_at
  actor_type
  actor_id
  event_type
  target_type
  target_id
  correlation_id
  causation_id
  payload_json
```

### Permission Policy

```text
permission_policy
  id
  workspace_id
  agent_id
  action_type
  scope_json
  risk_threshold
  decision_kind
  expires_at
  created_by
  created_at
  revoked_at
```

## Event Types

Task events:

- `task.created`
- `task.updated`
- `task.assigned`
- `task.status_changed`
- `task.completed`
- `task.failed`
- `task.canceled`

Approval events:

- `approval.requested`
- `approval.decided`
- `approval.expired`
- `approval.evidence_requested`

Agent events:

- `agent.registered`
- `agent.heartbeat`
- `agent.availability_changed`
- `agent.health_changed`
- `agent.paused`
- `agent.resumed`
- `agent.failed`

Artifact events:

- `artifact.created`
- `artifact.updated`

Policy events:

- `permission_policy.suggested`
- `permission_policy.created`
- `permission_policy.revoked`

## Projections

Maintain projections for fast UI reads:

- Active task list.
- Pending approvals.
- Agent health summary.
- Recent high-priority activity.
- Blocked work summary.

These projections can be rebuilt from events if needed, but the first version can update them transactionally with command handlers.

## Versioning

Use optimistic concurrency for task and approval updates:

- Each mutable row has a `version`.
- Commands include the last known version when modifying critical records.
- Backend rejects stale writes with a conflict error.

## Data Retention

Default:

- Keep all events locally.
- Allow future compaction for low-value heartbeat events.
- Preserve approval and task decision events permanently unless the user explicitly purges a workspace.

## Sync-Ready Boundaries

Even before cloud sync exists:

- Use stable ids.
- Store timestamps in UTC.
- Keep actor identity explicit.
- Keep event payloads schema-versioned.
- Avoid assuming single device forever in the data model.
