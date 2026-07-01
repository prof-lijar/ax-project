# Product Requirements

## Personas

Primary operator:

- Owns project outcomes.
- Reviews recommendations and approves actions.
- Assigns or redirects work among agents.
- Needs fast situational awareness and low-friction decisions.

Agent supervisor:

- Configures agent capabilities, risk levels, schedules, and permissions.
- Investigates agent failures or weak output.
- Needs logs, run history, and health indicators.

Builder:

- Connects new agents and tools.
- Needs clear integration boundaries, task schemas, and event contracts.

## Core Jobs

- See all active agents and whether they are healthy, idle, busy, blocked, or waiting for approval.
- Convert a human request or system signal into a task.
- Assign a task to a capable agent.
- Review agent plan, evidence, and proposed action.
- Approve, reject, modify, or delegate an approval request.
- Pause or resume an agent safely.
- Inspect what happened on a task after the fact.

## Feature Set

### Command Center

The default screen should show:

- Pending approvals.
- Active tasks.
- Blocked tasks.
- Agent health.
- Recent high-signal events.
- System risk warnings.

### Agent Directory

Each agent has:

- Name and role.
- Capabilities.
- Availability.
- Current task.
- Recent reliability signals.
- Permission profile.
- Last heartbeat.

### Task Workspace

Each task has:

- Goal.
- Owner agent or human owner.
- Status.
- Priority.
- Context.
- Timeline.
- Artifacts and evidence.
- Related approvals.
- Next action.

### Approval Queue

Each approval request has:

- Requested action.
- Requesting agent.
- Risk level.
- Evidence.
- Scope of permission.
- Expiration.
- Decision options.
- Consequences of approval or rejection.

### Activity Timeline

The timeline shows:

- Task creation.
- Assignment changes.
- Agent status transitions.
- Approval requests and decisions.
- Tool calls or future integration actions.
- Failures and retries.

## Non-Goals

- Replacing a full project management suite.
- Hiding agent uncertainty behind confident summaries.
- Making chat the only way to control work.
- Requiring cloud services for the first local build.

## Quality Requirements

- UI remains responsive with background agent activity.
- Critical decisions are recoverable after app restart.
- No destructive action can occur without an auditable approval in stage one.
- The system clearly distinguishes agent suggestion, agent execution, and human decision.

