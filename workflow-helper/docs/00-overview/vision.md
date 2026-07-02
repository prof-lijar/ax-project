# Vision

## Product Statement

AX Project is a desktop Agent Control Room for coordinating human work with always-on agents. The application helps a human operator understand what agents are doing, approve risky actions, assign work, inspect evidence, and maintain accountability.

The first version should make agent collaboration observable and controllable before it tries to make agents more autonomous.

## Why Desktop

A Tauri desktop application is appropriate because AX Project needs:

- Local-first state and fast interaction.
- Long-running background coordination.
- Native notifications and tray presence.
- Secure access to local project folders, credentials, logs, and developer tools.
- A persistent workspace that feels closer to an IDE or control room than a web dashboard.

## Operating Principles

- Human authority is explicit. Agents can suggest, prepare, and execute only within granted permission.
- Every important action leaves an event trail.
- The app optimizes for repeated operational command, not marketing polish.
- Agents are treated as workers with capabilities, limits, workload, confidence, and history.
- Approvals are first-class workflow objects, not modal interruptions scattered through the UI.
- The system should degrade gracefully when agents are offline, slow, or uncertain.

## Signature Experience

AX Project should be recognizable through one central pattern: the Mission Control surface.

The Mission Control surface combines:

- Agent lanes: compact live rows showing each agent's assignment, availability, health, and blockers.
- Decision stack: the approvals and human inputs that currently control forward progress.
- Risk radar: a small ordered view of high-risk proposed actions, degraded agents, and stale work.
- Mission timeline: a chronological trace of meaningful events across tasks and agents.

This pattern should guide the rest of the app. Tasks, approvals, and agents can have dedicated screens, but the first impression should be that the human is commanding a living system.

## Stage-One Scope

In scope:

- Desktop shell and navigation model.
- Agent registry and status model.
- Task inbox and task detail workflow.
- Approval queue and decision history.
- Human assignment and reassignment flow.
- Event timeline for tasks and agents.
- Local persistence.
- Integration-ready command boundary for future agent runtimes.

Out of scope for stage one:

- Full autonomous task execution.
- Marketplace of third-party agents.
- Multi-user collaboration server.
- Billing, organization administration, and cloud sync.
- Complex project management features unrelated to agent supervision.

## Success Criteria

The first usable build succeeds if a user can answer these questions within seconds:

- What are my agents doing?
- What needs my approval?
- Which work is blocked?
- Which agent owns this task?
- Why did the system recommend this action?
- What happened previously?
