---
name: evaluate-agent-systems
description: Evaluate, test, score, and review multi-agent systems and long-running agent workflows. Use when Codex needs to design evals, run behavioral test cases, inspect traces, find coordination failures, measure completion quality, validate handoffs, or decide whether an agent workflow is ready to ship.
---

# Evaluate Agent Systems

## Overview

Use this skill to evaluate whether a multi-agent workflow actually satisfies the mission, not just whether individual agents produced plausible outputs. Evaluation should produce evidence, failure cases, and release recommendations.

## Evaluation Plan

1. Restate the mission and acceptance criteria.
2. Identify observable behaviors that prove or disprove each criterion.
3. Build test cases that cover happy paths, ambiguous inputs, tool failures, partial completion, conflicting agent outputs, and interruption recovery.
4. Define scoring before running the workflow.
5. Inspect artifacts, logs, traces, and final outputs.
6. Report findings with severity, evidence, likely cause, and recommended fix.

## What To Evaluate

- Task decomposition quality.
- Role clarity and non-overlap.
- Handoff completeness.
- Tool permission and usage discipline.
- State persistence and resume behavior.
- Loop prevention and stop conditions.
- Correctness of final merged result.
- Coverage of acceptance criteria.
- User-facing clarity and honesty about residual risk.

## Scoring

Use a simple rubric unless the repo already has one:

- `pass`: Meets the criterion with evidence.
- `warn`: Mostly meets the criterion but has a limitation or weak evidence.
- `fail`: Does not meet the criterion or evidence contradicts the claim.
- `blocked`: Cannot evaluate because required artifact, environment, or permission is missing.

Prefer criterion-level scores over one aggregate score. Aggregate scores hide actionable failures.

## Report Format

Lead with findings:

```markdown
Finding:
Severity:
Evidence:
Impact:
Recommendation:
```

Then include:

- Tested scenarios.
- Commands or traces inspected.
- Criteria results.
- Residual risk.
- Suggested next evaluation.

## References

Read `references/evaluation-rubrics.md` when creating a reusable eval suite, scoring matrix, or release gate for a multi-agent workflow.
