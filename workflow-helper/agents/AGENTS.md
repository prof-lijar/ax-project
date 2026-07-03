# Agents Folder Instructions

This folder is a local workspace for designing, building, orchestrating, and evaluating long-running multi-agent systems. Keep agent instructions and skills scoped to this folder unless the user explicitly asks to install or modify global Codex configuration.

## Scope

- Apply these instructions only within this `agents` folder and its descendants.
- Keep reusable project skills in `.agents/skills/`.
- Do not write to `~/.codex/skills`, repo parents, or global agent config for this project unless explicitly requested.
- Do not create project skills in `.codex/skills` or top-level `skills/`; this workspace keeps skills under `.agents/skills/`.
- Treat `.agents/` as workspace-local agent configuration and metadata; do not assume global semantics without checking existing files first.

## Working Style

- Prefer small, composable agent workflows with explicit owner roles, handoff contracts, and verification gates.
- For long-running work, maintain durable state: goals, assumptions, decisions, open questions, artifacts, checkpoints, and recovery steps.
- Use concrete acceptance criteria before building or evaluating an agent workflow.
- Preserve user changes. If local files changed outside the current task, work with them rather than reverting them.

## Multi-Agent Design Defaults

- Define each agent by responsibility, authority, inputs, outputs, tools, stop conditions, and escalation rules.
- Keep orchestration separate from implementation and evaluation.
- Prefer deterministic interfaces between agents: structured task briefs, result schemas, logs, and artifact paths.
- Include a supervisor or coordinator when work spans multiple agents, long time horizons, or multiple repos/services.
- Include evaluator passes for behavioral regressions, missed requirements, tool misuse, loops, and weak handoffs.

## Engineering Defaults

- Read the local tree before creating structure.
- Use `rg` or `rg --files` for searching when available.
- Keep edits narrowly scoped and validate with the fastest meaningful checks.
- Add tests, fixtures, or evaluation cases when behavior is shared, stateful, or likely to regress.

## Local Skills

Use the project-local skills in `.agents/skills/` when the task matches them:

- `$orchestrate-multi-agents` for planning, coordinating, checkpointing, and operating multi-agent work.
- `$engineer-agent-systems` for implementing the agent runtime, contracts, state, tools, and observability.
- `$evaluate-agent-systems` for designing and running evaluations of multi-agent behavior.
