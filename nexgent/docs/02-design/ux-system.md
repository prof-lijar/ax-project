# UX System

## Design Position

AX Project should feel like a calm co-worker workspace for real work. The interface should be simple, legible, and fast. Avoid marketing-style hero sections, decorative dashboards, dense tables as the default surface, and empty explanatory panels.

The signature surface is Mission Control: one clear next decision, current work, co-worker presence, and recent activity arranged so the human can keep work moving without opening chat.

## Information Architecture

Primary navigation:

- Mission Control
- Tasks
- Approvals
- Team
- Activity
- Settings

Secondary surfaces:

- Task detail drawer or full page.
- Approval decision panel.
- Co-worker profile.
- Event detail inspector.
- Global command palette.

## First Screen

The first screen is Mission Control. It should immediately expose:

- Pending approvals grouped by risk and age.
- Co-workers grouped by presence, current focus, and blockers.
- Active missions grouped by blocked, waiting, and running.
- A short recent activity feed filtered to important changes.
- A create-task control.

No landing page is needed.

## Layout Model

Use a stable three-zone desktop layout:

- Left rail: primary navigation and system status.
- Main work area: selected queue, table, board, or detail page.
- Right inspector: selected task, approval, agent, or event details.

The right inspector can collapse on smaller widths. On narrow windows, use a two-level navigation model where lists and details become separate views.

## Screen Details

### Mission Control

Recommended layout:

- Top command strip: global search, create task, emergency pause, notification status.
- Primary decision panel: the next approval or human input request.
- Current work: a short list of active or blocked work.
- Co-worker area: people-like presence cards with role, focus, availability, and blockers.
- Recent activity: a short trace of important changes.

Hierarchy:

1. Decisions that unblock work.
2. Risk that could cause harm or failed execution.
3. Running work and recent changes.

### Tasks

Task list columns:

- Priority
- Status
- Title
- Owner
- Risk
- Last activity
- Next action

Task detail:

- Goal and status header.
- Current owner and next action.
- Context and artifacts.
- Related approvals.
- Timeline.

### Approvals

Approval list columns:

- Risk
- Age
- Requested action
- Agent
- Task
- Expiration

Approval detail:

- Decision controls at the top.
- Action scope.
- Evidence.
- Risk explanation.
- Alternatives.
- Timeline.

### Team

Team surface:

- Name
- Role
- Presence
- Current focus
- Blockers
- Last signal

Co-worker detail:

- Role and capability map.
- Permission profile.
- Current and recent work.
- Health timeline.
- Pause/resume controls.

## Interaction Principles

- Use tables for scan-heavy work.
- Use drawers for quick inspection and full pages for deep investigation.
- Keep approval actions visible without scrolling.
- Show exact action scope before approval.
- Offer scoped approval options without hiding risk.
- Group repeated low-risk approvals into a single decision when policy permits.
- Preserve keyboard navigation for queue processing.
- Prefer inline status and compact badges over verbose text.
- Use native notifications only for high-priority or time-sensitive events.

## Visual System

Recommended visual direction:

- Neutral base with restrained semantic colors.
- Use red only for destructive or high-risk states.
- Use amber for waiting, review, and degraded states.
- Use green for completed or healthy states.
- Use blue sparingly for active selection and primary actions.
- Avoid a single-hue dominant palette.

Components:

- Icon buttons for common commands.
- Segmented controls for view modes.
- Toggles for agent pause and permission settings.
- Sliders or numeric steppers for thresholds.
- Tooltips for compact controls.
- Badges for status, risk, and capability.

## Empty States

Empty states should be operational, not promotional:

- No approvals: show recent completed decisions and policy status.
- No active tasks: show create task and scheduled tasks.
- No agents: show connect/mock agent setup.
