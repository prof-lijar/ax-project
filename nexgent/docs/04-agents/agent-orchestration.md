# Agent Orchestration

## Orchestration Goal

The first stage should model agents clearly even before full execution exists. The app needs to know who agents are, what they can do, whether they are healthy, what work they own, and when they need human permission.

## Agent Registry

Each agent record should include:

- Stable id.
- Display name.
- Role.
- Description.
- Capabilities.
- Runtime adapter.
- Status.
- Permission profile.
- Workload limits.
- Last heartbeat.
- Reliability metrics.

Example capabilities:

- `code.review`
- `code.modify`
- `docs.write`
- `research.summarize`
- `task.plan`
- `test.run`
- `shell.propose`
- `shell.execute`
- `file.read`
- `file.write`

## Runtime Adapters

Adapters isolate transport from product behavior.

Adapter responsibilities:

- Start or connect to an agent.
- Send assigned task.
- Receive status updates.
- Receive messages, artifacts, and approval requests.
- Pause, resume, or stop work.
- Report heartbeat and failure state.

Potential adapters:

- Mock adapter for stage-one UI development.
- Local process adapter.
- HTTP API adapter.
- MCP-style tool adapter.
- Future cloud orchestration adapter.

## Permission Profiles

An agent permission profile defines what the agent may do without explicit approval.

Suggested levels:

- Observe: can read allowed context and produce recommendations.
- Prepare: can draft plans, patches, commands, or messages.
- Execute low-risk: can perform actions marked low-risk by policy.
- Approval required: can request permission for scoped actions.
- Paused: cannot start or continue work.

Permission rules should consider:

- Action type.
- Target resource.
- Risk level.
- Task priority.
- Agent trust level.
- Recent failure history.
- Human override.

## Approval Requests

Agents create approval requests when a proposed action exceeds their current permission.

Approval request fields:

- Requested action.
- Action parameters.
- Scope.
- Risk level.
- Evidence.
- Alternatives.
- Requesting agent.
- Related task.
- Expiration.
- Policy reason.

Approval requests are not chat messages. They are actionable workflow objects.

## Approval Load Management

The orchestration layer should prevent approval fatigue before requests reach the UI.

Rules:

- Bundle compatible approvals when they share task, requesting agent, action type, target scope, and risk level.
- Prefer one scoped approval over many identical approvals.
- Suggest policy promotion only after repeated successful approvals with no rejection, failure, or scope expansion.
- Never bundle high-risk destructive actions unless every action target is visible in the decision view.
- Expire stale approvals and ask the agent to re-plan when context has changed.
- Suppress duplicate approval requests by idempotency key, action payload, and target scope.

Scoped approval options:

- Once: only the exact requested action.
- For task: same action type and target scope within the current task.
- Timeboxed: same action type and target scope until expiration.
- Policy suggestion: convert a repeated pattern into a proposed permission rule that still requires human approval.

## Supervision Controls

Human operators need:

- Pause agent.
- Resume agent.
- Reassign task.
- Lower permission level.
- Request more evidence.
- Mark output unacceptable.
- Add instruction to current task.
- Cancel task.

## Agent Availability and Health

Health signals:

- Heartbeat freshness.
- Current task progress.
- Error rate.
- Approval rejection rate.
- Average time blocked.
- Adapter connectivity.
- Resource consumption when available.

Availability states:

- Idle
- Busy
- Waiting
- Offline
- Paused

Health states:

- Healthy
- Degraded
- Offline

## Failure Handling

Failures should create events and update projections.

Common failure categories:

- Adapter unavailable.
- Agent timeout.
- Invalid output.
- Policy violation.
- Missing context.
- User rejected action.
- Runtime crash.

Recovery actions:

- Retry with same agent.
- Retry with different agent.
- Request more context.
- Escalate to human.
- Cancel task.
- Pause agent.
