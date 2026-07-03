---
name: orchestrate-multi-agents
description: Plan, coordinate, and operate long-running multi-agent workflows. Use when Codex needs to decompose work across specialist agents, define handoff contracts, manage durable state and checkpoints, recover from interruptions, supervise parallel work, or keep an agent team aligned through planning, implementation, review, and evaluation.
---

# Orchestrate Multi-Agents

## Overview

Use this skill to turn ambiguous multi-agent work into a controlled operating plan with clear roles, artifacts, checkpoints, and evaluation gates. Optimize for durable progress: every agent should know what it owns, what it must return, and how the coordinator decides the next step.

## Operating Loop

1. Define the mission in one sentence, then list concrete acceptance criteria.
2. Identify required agent roles and keep them minimal.
3. Write a task brief for each agent with inputs, outputs, allowed tools, constraints, and stop conditions.
4. Define handoff contracts before spawning or assigning work.
5. Establish checkpoints for long-running work: current goal, completed artifacts, open questions, risks, and next action.
6. Run implementation and evaluation as separate phases unless the user explicitly asks for exploration only.
7. Merge results through a coordinator decision, not by concatenating agent outputs.

## Role Design

Use only the roles the task needs. Common roles:

- **Coordinator**: owns the plan, state, sequencing, conflict resolution, and final response.
- **Researcher**: gathers source context, constraints, prior art, APIs, and repo patterns.
- **Engineer**: implements scoped changes and keeps diffs reviewable.
- **Evaluator**: tests behavior against acceptance criteria and looks for regressions.
- **Reviewer**: checks correctness, maintainability, risk, and missing verification.

For each role, specify:

- Responsibility and decision authority.
- Inputs it may rely on.
- Required output format.
- Tools it may use.
- Conditions that require escalation to the coordinator.

## Handoff Contract

Require every agent result to include:

- `summary`: concise result.
- `artifacts`: files, commands, logs, URLs, or data produced.
- `decisions`: choices made and why.
- `open_questions`: unresolved issues.
- `risks`: likely failure modes or weak assumptions.
- `next_step`: recommended action.

Prefer structured text or JSON when another agent or script will consume the output.

## Long-Running State

Maintain a checkpoint artifact when work may span interruptions, many steps, or multiple agents. Include:

- Current objective and acceptance criteria.
- Agent roster and active assignments.
- Completed work and verified evidence.
- Pending work and blocked work.
- Key decisions and constraints.
- Recovery instructions: exact next command or task to resume.

## Coordination Rules

- Spawn or delegate only when parallelism, independence, or evaluation quality justifies the overhead.
- Keep task briefs small enough that agents cannot reinterpret the mission.
- Do not let implementation agents silently change acceptance criteria.
- Reconcile conflicts by returning to source artifacts, tests, and user intent.
- End with evidence: what changed, what passed, what remains risky.

## References

Read `references/coordination-patterns.md` when designing a reusable coordinator, supervisor loop, checkpoint format, or handoff schema.
