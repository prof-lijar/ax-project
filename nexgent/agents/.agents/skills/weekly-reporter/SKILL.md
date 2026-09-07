---
name: weekly-reporter
description: Implement, review, debug, or operate the Ansimk weekly-reporter workflow, its private FastAPI raw-data source, deterministic ward metrics, grounded Korean LLM summaries, fallback policy, and related tests or documentation. Use for changes involving ansimk_weekly_reporter, weekly report calculations, report source APIs, or warm guardian-facing Korean copy.
---

# Weekly Reporter

## Workflow

1. Read `docs/ax-agents-architecture.md` and the current weekly-report code.
2. Read `references/source-contract.md` before changing data access,
   calculations, paging, API models, or configuration.
3. Read `references/narrative-style-guide.md` before changing prompts,
   qualitative facts, validation, fallback wording, or evaluations.
4. Keep raw numeric calculation deterministic and upstream of the LLM.
5. Keep provider-neutral database code in `packages/integrations`, deployable
   HTTP composition in `apps/weekly_report_api`, and reporter-specific behavior
   under `workflows/weekly_report`.
6. Preserve the `ansimk_weekly_reporter` graph ID and compatibility
   `metrics.current/previous/delta.danger_days` fields unless a versioned
   migration is explicitly approved.
7. Add or update unit, contract, integration, and evaluation coverage in
   proportion to the changed boundary.
8. Update `docs/ax-agents-architecture.md`, `docs/README.md`, and the weekly
   reporter implementation document for material architecture changes.
9. Send completed reports only through the shared `SlackService` and the
   workflow-local `slack_delivery` boundary. Preserve explicit human approval,
   an approved default or configured logical destination, and separation from
   graph retries.

## Guardrails

- Never expose arbitrary SQL as a model-callable tool.
- Never put database credentials, raw rows, management notes, evaluation notes,
  or dispatch descriptions in graph state or model prompts.
- Treat spreadsheet fields and thresholds as non-authoritative unless product
  owners explicitly promote them to a versioned backend rule.
- Render every number from validated Python contracts, never from model prose.
- Keep interactive requests bounded to twenty-five wards, bulk source pages
  bounded to one hundred wards, and preserve validated opaque cursor semantics.
- Keep summaries warm and calm without diagnosis, cause attribution, emergency
  certainty, accident certainty, categorical danger wording, or invented facts.
- Validate model JSON once, allow one bounded corrective attempt, then use and
  disclose the deterministic fallback.

## Verification

Run focused tests first, then Ruff, the full test suite, LangGraph validation,
Compose rendering, and the skill validator. A live database check requires
operator-provided environment secrets and must remain read-only.
