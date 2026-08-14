# Workflow modules

Each workflow owns its graph topology, state, nodes, prompts, and any local
agent subgraphs. Shared infrastructure belongs in `packages/`; deployable
processes belong in `apps/`.

Use this shape when implementing a workflow:

```text
workflow_name/
  __init__.py       # intentionally small public exports
  graph.py          # compiled graph or graph factory
  state.py          # minimal workflow-local state
  nodes.py          # deterministic and agent-backed nodes
  agents/           # optional workflow-local specialist definitions
  prompts/          # optional versioned prompt assets
  policies.py       # optional workflow-specific routing/approval policy
  tests/            # optional colocated fixtures; shared suites stay in /tests
```

Create optional directories only when they contain real code. A workflow may
depend on shared packages, but shared packages must never import a workflow.

The `orchestrator` is reserved for cross-workflow coordination that cannot be
expressed as deterministic application routing. Planned workflows are
`risk_monitoring`, `call_recommendation`, and `device_management` remain planned.
`weekly_report` is implemented as the manually triggered
`ansimk_weekly_reporter` batch graph with deterministic calculations, bounded
per-ward subgraphs, database MCP danger-day input, Korean model-written
narrative, and template fallback.
