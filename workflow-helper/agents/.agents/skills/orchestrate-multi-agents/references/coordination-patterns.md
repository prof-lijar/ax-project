# Coordination Patterns

## Coordinator State

Use a compact state document for long-running workflows:

```yaml
objective: ""
acceptance_criteria: []
agents:
  - name: ""
    role: ""
    status: pending
    current_task: ""
artifacts: []
decisions: []
risks: []
blocked: []
next_action: ""
```

## Task Brief Template

```markdown
Mission:
Context:
Inputs:
Output Required:
Constraints:
Tools Allowed:
Stop Conditions:
Escalate If:
```

## Result Template

```markdown
Summary:
Artifacts:
Decisions:
Evidence:
Open Questions:
Risks:
Next Step:
```

## Common Failure Modes

- Agents duplicate work because ownership is vague.
- Agents optimize locally and break the global acceptance criteria.
- Long-running work loses state after interruption.
- Handoffs omit evidence, forcing the coordinator to rediscover context.
- Evaluation starts too late and only checks happy paths.
