---
name: engineer-agent-systems
description: Build and modify multi-agent systems, including agent contracts, orchestration runtimes, tool adapters, state stores, queues, prompts, schemas, observability, and recovery logic. Use when Codex needs to implement or refactor the engineering pieces that make multiple agents work together reliably over long-running tasks.
---

# Engineer Agent Systems

## Overview

Use this skill to implement multi-agent systems with explicit contracts, durable state, clear tool boundaries, and testable behavior. Favor simple runtime primitives before adding framework complexity.

## Build Order

1. Read the existing codebase and identify local patterns for agents, tasks, tools, queues, state, and tests.
2. Define the runtime contract before implementation: task input, agent output, state transitions, error shape, and retry behavior.
3. Implement the smallest vertical path first: create task, assign agent, run step, record result, evaluate completion.
4. Add observability while building: structured logs, trace IDs, artifact paths, and status transitions.
5. Add recovery behavior for interruption, timeout, failed tool calls, partial outputs, and duplicate work.
6. Validate with focused tests and at least one realistic multi-step scenario.

## Core Interfaces

Prefer typed or schema-validated interfaces for:

- Agent definition: name, role, model/runtime, tools, input schema, output schema, stop conditions.
- Task envelope: id, objective, context, constraints, assigned agent, priority, status, attempt count.
- Message or event: source, target, type, payload, timestamp, correlation id.
- Artifact reference: path or URI, type, owner, checksum or version when available.
- Evaluation result: criterion, status, evidence, severity, recommendation.

## State And Recovery

- Persist enough state to resume without re-running completed work.
- Make writes idempotent where possible.
- Use explicit statuses such as `pending`, `running`, `blocked`, `failed`, `completed`, and `verified`.
- Record why a retry is safe before retrying a tool or agent step.
- Store raw agent outputs separately from normalized coordinator decisions.

## Engineering Constraints

- Keep orchestration logic separate from agent prompts and model provider adapters.
- Keep tool permissions narrow and visible.
- Do not hide long-running loops behind unbounded recursion or open-ended polling.
- Make stop conditions enforceable in code, not only in prose.
- Treat evaluator results as first-class inputs to release or continuation decisions.

## Testing

Include tests for the highest-risk behavior:

- Contract validation rejects malformed agent outputs.
- Coordinator handles partial, failed, and conflicting results.
- Long-running state resumes from a checkpoint.
- Agent handoffs include required artifacts and evidence.
- Evaluator failures prevent completion when acceptance criteria are unmet.

## References

Read `references/implementation-checklist.md` before implementing a new runtime, modifying shared contracts, or adding persistence and recovery behavior.
