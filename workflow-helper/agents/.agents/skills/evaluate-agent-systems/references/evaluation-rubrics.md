# Evaluation Rubrics

## Coordination Rubric

| Criterion | Pass Evidence | Fail Signal |
| --- | --- | --- |
| Role clarity | Each agent has distinct ownership | Duplicate or conflicting work |
| Handoff quality | Outputs include artifacts, evidence, risks, next step | Coordinator must rediscover context |
| State durability | Workflow resumes from checkpoint | Progress is lost after interruption |
| Stop discipline | Agents stop at defined conditions | Open-ended loops or repeated retries |
| Merge quality | Final decision resolves conflicts | Outputs are concatenated without judgment |

## Engineering Rubric

| Criterion | Pass Evidence | Fail Signal |
| --- | --- | --- |
| Contract validation | Bad outputs are rejected or repaired explicitly | Malformed outputs flow downstream |
| Observability | Logs show task, agent, event, artifact, status | Failures require rerunning to inspect |
| Recovery | Timeout, retry, cancel, and resume paths exist | Manual cleanup is required |
| Test coverage | Happy path and failure path are exercised | Only prompt text is reviewed |

## Release Gate

Do not mark a multi-agent workflow ready if:

- Any critical acceptance criterion fails.
- Evaluator cannot inspect required artifacts.
- Long-running state cannot resume after interruption.
- Tool permissions are broader than the workflow needs.
- Known loops or duplicate work are unbounded.
