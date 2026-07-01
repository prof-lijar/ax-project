# UX System

## Design Position

AX Project should feel like an operations console for real work. The interface should be dense, calm, legible, and fast. Avoid marketing-style hero sections, decorative cards, and empty explanatory panels.

## Information Architecture

Primary navigation:

- Command Center
- Tasks
- Approvals
- Agents
- Activity
- Settings

Secondary surfaces:

- Task detail drawer or full page.
- Approval decision panel.
- Agent profile.
- Event detail inspector.
- Global command palette.

## First Screen

The first screen is the Command Center. It should immediately expose:

- Pending approvals grouped by risk and age.
- Active tasks grouped by status.
- Agent roster with compact health signals.
- Recent events filtered to important changes.
- A create-task control.

No landing page is needed.

## Layout Model

Use a stable three-zone desktop layout:

- Left rail: primary navigation and system status.
- Main work area: selected queue, table, board, or detail page.
- Right inspector: selected task, approval, agent, or event details.

The right inspector can collapse on smaller widths. On narrow windows, use a two-level navigation model where lists and details become separate views.

## Screen Details

### Command Center

Recommended layout:

- Top strip: global search, create task, emergency pause, notification status.
- Main left: approval queue and blocked tasks.
- Main center: active task table.
- Main right: agent health and recent events.

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

### Agents

Agent list columns:

- Status
- Name
- Role
- Current task
- Queue depth
- Last heartbeat
- Reliability

Agent detail:

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

