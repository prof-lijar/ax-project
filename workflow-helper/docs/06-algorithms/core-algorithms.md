# Core Algorithms

## Task Classification

Inputs:

- Task title and goal.
- User-selected priority.
- Referenced resources.
- Required capabilities.
- Expected action type.
- Historical similar tasks.

Outputs:

- Capability requirements.
- Initial risk level.
- Suggested owner.
- Missing context prompts.

Basic algorithm:

1. Extract explicit capability hints from task metadata.
2. Match goal text against capability keywords and past task labels.
3. Estimate risk from target resources and action verbs.
4. If confidence is low, classify as ready but mark missing context.
5. Produce assignment candidates.

## Agent Assignment Scoring

Score each candidate agent with weighted factors:

```text
score =
  capability_match * 0.35 +
  availability * 0.20 +
  reliability * 0.20 +
  workload_fit * 0.15 +
  recency_fit * 0.10 -
  risk_penalty
```

Factor definitions:

- `capability_match`: how well agent capabilities satisfy task requirements.
- `availability`: idle or soon available agents score higher.
- `reliability`: recent success rate, rejection rate, and failure rate.
- `workload_fit`: lower queue pressure scores higher.
- `recency_fit`: agent familiarity with related context.
- `risk_penalty`: penalty when task risk exceeds agent trust or permission.

Tie-breakers:

1. Higher capability match.
2. Lower current workload.
3. More recent success on similar task.
4. Stable deterministic id order.

## Approval Gating

Goal: decide whether an agent action can proceed automatically or needs human approval.

Inputs:

- Agent permission profile.
- Action type.
- Target resource.
- Risk level.
- Task status and priority.
- Policy overrides.
- Recent agent health.

Decision results:

- Allowed.
- Approval required.
- Denied.
- Agent paused.

Algorithm:

1. If agent is paused or offline, deny action.
2. If action type is globally denied, deny action.
3. If action target is outside allowed scope, require approval or deny based on policy.
4. If risk level is greater than permission threshold, require approval.
5. If recent health is degraded, require approval for actions above low risk.
6. If task is canceled, deny action.
7. Otherwise allow action and emit a policy event.

## Approval Priority

Approval queue ordering:

```text
priority_score =
  risk_weight +
  age_weight +
  blocked_task_weight +
  deadline_weight +
  dependency_weight
```

Suggested weights:

- Critical risk: +100
- High risk: +70
- Medium risk: +40
- Low risk: +10
- Blocking active task: +30
- Expiring within 15 minutes: +25
- Older than 1 hour: +15
- Blocks multiple tasks: +10 per dependent task, capped at +40

Sort descending by priority score, then oldest request first.

## Notification Routing

Notify the user only when attention is valuable.

Desktop notification triggers:

- Critical approval requested.
- Approval expires soon.
- Agent goes offline while owning active work.
- Task fails after retry.
- Emergency pause activated.

Do not notify for:

- Normal heartbeat.
- Low-risk completed events.
- Minor timeline updates while the app is focused.

## Context Selection

When an agent or human opens a task, show the most relevant context first.

Ranking factors:

- Explicitly attached artifacts.
- Recent events on the same task.
- Open approvals.
- Agent-generated evidence.
- Similar completed tasks.
- User notes.

Algorithm:

1. Always include task goal, current status, owner, and open approvals.
2. Add artifacts directly attached to the task.
3. Add the latest meaningful events, excluding routine heartbeat noise.
4. Add related task references if similarity exceeds threshold.
5. Keep a compact summary for list views and full detail for inspector views.

## Stale Work Detection

A task is stale when no meaningful progress has occurred within the expected interval.

Inputs:

- Task priority.
- Agent status.
- Last meaningful event.
- Expected duration.
- Current blockers.

Rules:

- Running high-priority task with no update for 15 minutes: attention needed.
- Running normal task with no update for 60 minutes: stale.
- Waiting for approval: not stale, but approval may become urgent.
- Agent offline and assigned active task: blocked.

## Event Deduplication

Because agent runtimes may retry updates, backend event append should deduplicate by:

- Correlation id.
- Event type.
- Target id.
- Adapter-provided idempotency key when available.

If a duplicate arrives, return success with the existing event id.

