# Implementation Checklist

## Contracts

- Define task, agent, result, artifact, and evaluation schemas.
- Version schemas if outputs may be stored or replayed.
- Validate every cross-agent output at the boundary.

## Runtime

- Use correlation IDs for multi-agent workflows.
- Persist task status transitions.
- Keep raw logs and normalized summaries separate.
- Make retries bounded and visible.
- Provide cancellation and timeout paths.

## Tools

- Register tools by capability and permission scope.
- Log tool name, inputs summary, outputs summary, and failure type.
- Avoid passing secrets through agent-visible prompts.

## Observability

- Emit structured events for assignment, start, tool call, result, evaluation, retry, and completion.
- Include artifact paths in final summaries.
- Make failure states inspectable without rerunning the workflow.

## Verification

- Unit test schema validation and state transitions.
- Integration test a multi-agent happy path and at least one failure path.
- Add regression fixtures for known bad outputs or loops.
