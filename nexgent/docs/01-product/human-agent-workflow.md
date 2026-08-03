# Human-Agent Workflow

## Primary Loop

1. Work enters the system as a human-created task, scheduled task, integration event, or agent-discovered opportunity.
2. The task is classified by goal, required capabilities, risk, urgency, and context.
3. The assignment engine recommends an agent or human owner.
4. The selected agent prepares a plan or performs allowed low-risk work.
5. If the next action exceeds permission, an approval request is created.
6. The human approves, rejects, modifies, delegates, or asks for more evidence.
7. The agent continues, reports completion, or escalates blockage.
8. The event log preserves the full timeline.

## Approval Decision Types

- Approve once: allow only this specific action.
- Approve with constraints: allow action after modifying scope, target, or parameters.
- Approve for task: allow the same action type within this task and visible scope.
- Approve timeboxed: allow the same action type and scope until expiration.
- Reject: deny the action and require alternate plan.
- Request evidence: keep approval pending and ask agent for missing information.
- Delegate: assign decision to another human or future policy.
- Pause agent: stop the requesting agent from continuing related work.

## Task States

- Draft: created but not ready for assignment.
- Ready: has enough information to be assigned.
- Assigned: owner selected but work has not started.
- Running: active work is underway.
- Waiting for approval: blocked on a human decision.
- Waiting for input: blocked on missing human context.
- Blocked: cannot progress due to error, dependency, or unavailable capability.
- Completed: accepted result exists.
- Canceled: intentionally stopped.
- Failed: ended due to unrecoverable error.

## Agent Availability States

- Offline: no heartbeat.
- Idle: available for work.
- Busy: actively working.
- Waiting: blocked on human, dependency, rate limit, or scheduled delay.
- Paused: intentionally prevented from starting or continuing work.

## Agent Health States

- Healthy: heartbeats and recent behavior are within expected bounds.
- Degraded: alive but failing health checks or producing repeated errors.
- Offline: no heartbeat.

## Key User Journeys

### Review Morning Queue

The operator opens AX Project and sees pending approvals, overnight agent activity, failed tasks, and recommended next actions. They clear high-risk approvals first, reassign blocked work, and leave low-risk completed items for later review.

### Assign New Work

The operator creates a task with a goal and optional context. AX Project recommends agents based on capability, workload, and recent performance. The operator accepts the recommendation or manually chooses an agent.

### Approve Risky Action

An agent asks to run a future integration action. The approval view shows the requested action, exact scope, evidence, risk, and alternative options. The operator approves with constraints, and the decision is attached to the task timeline.

### Investigate Agent Behavior

The operator opens an agent profile, reviews recent tasks, failures, response latency, permission use, and blocked approvals. They pause the agent or adjust its permissions.
