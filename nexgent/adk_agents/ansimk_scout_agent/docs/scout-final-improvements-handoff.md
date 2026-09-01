# Scout Agent — Final Improvement Handoff

Date: 2026-08-31 (Asia/Seoul)

## Overview

This document covers only the following three final requested improvements:

1. Recurring Scheduling — Once / Daily / Weekly / Monthly
2. Summary & Key Findings Validation Against Fetched Source Content
3. Optional Additional Research Instructions

Current status:

- **Recurring Scheduling: COMPLETED**
- **Source-content / semantic grounding validation: NOT IMPLEMENTED — design completed and handed off**
- **Additional Research Instructions: COMPLETED**

# 1. Recurring Scheduling — COMPLETED

The existing one-time scheduling flow was extended to support **Once, Daily,
Weekly, and Monthly** schedules. Scheduling remains based on `Asia/Seoul`
(KST). Once preserves the existing one-time `DateTrigger` behavior; Daily,
Weekly, and Monthly use persistent KST `CronTrigger` rules.

After any recurring occurrence succeeds or fails, its schedule returns to
`pending`, remains active, and advances to its next occurrence instead of
becoming permanently terminal. The latest execution result is retained
separately in `scout_run` from the active schedule status. A recurring card can
therefore correctly show both **Pending** and **Latest run succeeded**. Pending
means that the recurring schedule is active and waiting for its next execution.

Recurrence configuration (`recurrence`, `schedule_time`, `day_of_week`, and
`day_of_month`) is persisted in SQLite. At startup, the scheduler reconciles
persisted records and reconstructs pending `DateTrigger` or `CronTrigger` jobs
by schedule UUID without duplicating records. Stale recurring occurrences are
advanced safely without a blind retry. Existing rows and requests that omit
recurrence remain compatible and default to Once.

Cancellation remains a persisted state transition rather than deletion. Only
a pending schedule can be cancelled; its APScheduler job is removed, its audit
row and latest result remain available, and running or otherwise terminal
schedules return a safe conflict. Monthly days that do not exist in a given
month are skipped, consistently with `CronTrigger` semantics—for example, a
day-31 schedule skips September.

Primary implementation and coverage are in:

- `scheduling-agent-poc/scheduling-agent/app/scout_schedule_models.py`
- `scheduling-agent-poc/scheduling-agent/app/scout_schedule_repository.py`
- `scheduling-agent-poc/scheduling-agent/app/scout_schedule_service.py`
- `scheduling-agent-poc/scheduling-agent/app/fast_api_app.py`
- `scheduling-agent-poc/scheduling-agent/tests/unit/test_scout_schedule_models.py`
- `scheduling-agent-poc/scheduling-agent/tests/unit/test_scout_schedule_repository.py`
- `scheduling-agent-poc/scheduling-agent/tests/unit/test_scout_schedule_service.py`
- `scheduling-agent-poc/scheduling-agent/tests/integration/test_scout_schedule_api.py`

## Recurrence Frontend UX

Daily, Weekly, and Monthly controls display a calculated next execution in KST
before the schedule is created. For Weekly, the selected current weekday plus
a future time resolves to today; the same weekday plus a past time resolves to
the following week. Monthly preview calculation skips invalid dates. Once UI
and behavior were preserved and do not show this recurring preview.

The preview is frontend-only. It does not change scheduling API payloads,
backend trigger behavior, or persistence. Its implementation and focused tests
are in:

- `nexgent/frontend/src/features/agents/ScoutWorkbenchPage.tsx`
- `nexgent/frontend/src/features/agents/ScoutWorkbenchPage.test.tsx`
- `nexgent/frontend/src/shared/api/scoutScheduleClient.ts`
- `nexgent/frontend/src/shared/api/scoutScheduleClient.test.ts`

Latest preview validation:

- focused Workbench tests: **39 passed**;
- full frontend suite: **220 passed**;
- TypeScript/Vite production build: **passed**;
- Rust desktop check: **passed**; and
- diff/whitespace checks: **passed**.

The recorded backend recurrence validation was **68 passed** across focused
recurrence model, SQLite migration/repository, scheduler service, and Scheduling
API tests. The broader non-live Scheduling POC unit/integration run was **95
passed**; the live ADK/model integration and hard-coded-port server E2E files
were excluded after their external boundaries did not become ready in the inert
test environment.

## Runtime Verification

Recurring Schedule ID `576a9ddb-55b8-47a5-8713-f723676dabc7` was verified as a
Daily schedule for 17:45 KST. It executed successfully in approximately 47
seconds and produced a result containing one source. After execution, the
schedule returned to Pending and its next run advanced to
`2026-09-01 17:45 KST`.

This demonstrated that recurring execution, latest-result persistence, and
next-occurrence advancement worked correctly.

# 2. Summary / Key Findings Validation Against Source Content — NOT IMPLEMENTED

**STATUS: NOT IMPLEMENTED**

Design and investigation were completed, but implementation was intentionally
left for the next engineer. No semantic grounding validator currently exists
in production.

## Problem

Existing Scout validation verifies the required report structure and source URL
provenance. It does **not** semantically verify that factual statements in
Summary and Key Findings are supported by the fetched article content. A report
can therefore cite a real fetched source while still containing an unsupported
generalization or an LLM-added claim.

## Observed Examples

### Example A — clearly unsupported generalization

A generated report stated:

> 현재는 연령과 소득 수준을 불문하고 사회적 고립이 심화되면서 광범위하게 발생하고 있습니다.

The source article discussed economic hardship and social isolation among
elderly people in Japan, but did not support the broader claim that solitary
death currently occurs regardless of age and income level. This claim should be
classified as unsupported or unverifiable.

### Example B — subtle expansion of source wording

A later AI-care report was mostly grounded in its source article but included
wording such as:

- “rapid emergency response”
- “efficient management of high-risk individuals”

The source supported related mechanisms—SOS detection, connection to a 24-hour
control center, 119 dispatch after confirming an emergency, and data-based
monitoring by social workers—but the generated wording slightly generalized or
expanded what the article explicitly stated. URL validation alone is therefore
not sufficient.

## Agreed Minimal Design

```text
Generate Markdown
→ existing deterministic heading/URL validation preflight
→ extract Summary paragraphs and Key Findings items
→ one semantic verifier call using retained FetchedPage.text
→ strict local/Python validation
→ existing save_report()
→ persist report.md only after acceptance
```

Evidence must come only from successfully fetched pages that are also listed in
the generated report's Sources section. The verifier should classify material
factual claims as:

- `supported`
- `unsupported`
- `contradicted`
- `unverifiable`
- `non_factual`

Every supported claim must provide an eligible source URL and a short verbatim
evidence excerpt. Python/application code must independently verify that every
expected report unit is present exactly once, that there are no duplicate or
unknown unit IDs, that evidence URLs belong to the allowed source mapping, that
each evidence excerpt actually occurs in retained `FetchedPage.text`, and that
every material factual claim is supported.

Do not trust a model-generated `overall_pass`. Application code must derive
final acceptance locally. Any unsupported, contradicted, or unverifiable
material factual claim must reject the report.

## Failure Behavior

The implementation must fail closed for:

- timeout;
- provider/model failure;
- empty response;
- invalid JSON;
- schema validation failure;
- incomplete unit coverage;
- duplicate or unknown unit IDs;
- invalid evidence URL;
- evidence excerpt not found in source text; and
- unsupported, contradicted, or unverifiable material factual claims.

On failure, stop before `save_report()` and do not create `report.md`. Do not
retry the verifier. Preserve the existing safe Scout failure / HTTP 502
contract. Never log article body text, evidence excerpts, or raw verifier
output.

## Proposed Minimal Implementation Scope

- `nexgent/adk_agents/ansimk_scout_agent/app/agent.py` — expose or reuse the
  existing configured LiteLLM factory without changing Scout Agent behavior.
- `nexgent/adk_agents/ansimk_scout_agent/app/tools/scout.py` — add a defensive
  accessor for successfully fetched `FetchedPage` data.
- `nexgent/adk_agents/ansimk_scout_agent/app/services/run_service.py` — run
  deterministic validation first, invoke grounding verification, and call
  `save_report()` only after acceptance.
- `nexgent/adk_agents/ansimk_scout_agent/app/services/grounding.py` — new module
  for strict verifier schemas, report-unit extraction, one-shot semantic
  verification, and deterministic result validation.

The minimal design should require no changes to the frontend, API endpoint
paths, API response models, visible Markdown report format, or scheduling
behavior.

## Verifier Constraints

- Reuse the existing configured LiteLLM model, endpoint, and API key.
- Do not create another ADK Agent or Runner.
- Make exactly one post-generation verifier model call, with no tools.
- Use `temperature = 0`, bounded output tokens, a dedicated timeout, and
  automatic retries disabled.
- Require a strict Pydantic structured response and JSON MIME when supported.
- Keep the existing Scout Agent `max_llm_calls=8` unchanged.

The verifier is a separate post-Agent call, so the theoretical maximum is **8
Scout Agent calls + 1 verifier call**. Before depending on structured output,
run one bounded smoke test against the configured internal model endpoint. Do
not add a runtime fallback that silently makes a second verifier call.

## Tests To Implement

Add:

- `nexgent/adk_agents/ansimk_scout_agent/tests/unit/test_grounding.py`
- additions to `nexgent/adk_agents/ansimk_scout_agent/tests/unit/test_scout_tools.py`
- additions to `nexgent/adk_agents/ansimk_scout_agent/tests/unit/test_run_service.py`
- additions to `nexgent/adk_agents/ansimk_scout_agent/tests/contract/test_api.py`

Cover supported, unsupported, contradicted, and unverifiable claims; exact unit
coverage; duplicate and unknown unit IDs; source eligibility; exact evidence
excerpt containment; malformed verifier responses; timeout/provider failure;
no retry; report persistence only after successful grounding; absence of
article/evidence content from logs; and preservation of the existing API
success/failure contract.

# 3. Additional Research Instructions — COMPLETED

The existing fixed `SCOUT_INSTRUCTION` system prompt was intentionally
preserved unchanged. This feature is not a second system prompt. The message
architecture is:

```text
SYSTEM:
existing fixed SCOUT_INSTRUCTION

USER:
Topic
+ Keywords
+ optional Additional research instructions
```

Run Now and Schedule share one textarea labeled **“Additional research
instructions”** with the helper **“Optional. Guides this run or schedule but
cannot change Scout's source and safety rules.”** Input is limited to 2,000
characters, surrounding whitespace is trimmed, blank content becomes
null/absent, and blank values are omitted from outgoing JSON.

Instructions remain subordinate role-user data. They are persisted for
scheduled jobs, participate in pending-schedule uniqueness, are forwarded by
the Scheduler to Scout at execution time, and are displayed on scheduled-job
cards. Legacy requests remain compatible, and additive nullable persistence
makes legacy schedules compatible. Existing source and safety rules remain
unchanged. Sensitive instruction content is not added to execution logs.

Relevant implementation areas are:

- **Scout backend:**
  `nexgent/adk_agents/ansimk_scout_agent/app/models.py`,
  `nexgent/adk_agents/ansimk_scout_agent/app/services/run_service.py`, and the
  unchanged fixed prompt in
  `nexgent/adk_agents/ansimk_scout_agent/app/agent.py`.
- **Scheduler:**
  `scheduling-agent-poc/scheduling-agent/app/scout_schedule_models.py`,
  `scheduling-agent-poc/scheduling-agent/app/scout_schedule_repository.py`,
  `scheduling-agent-poc/scheduling-agent/app/scout_schedule_service.py`,
  `scheduling-agent-poc/scheduling-agent/app/scout_api_client.py`, and
  `scheduling-agent-poc/scheduling-agent/app/fast_api_app.py`.
- **Frontend:**
  `nexgent/frontend/src/features/agents/ScoutWorkbenchPage.tsx`,
  `nexgent/frontend/src/shared/api/scoutClient.ts`, and
  `nexgent/frontend/src/shared/api/scoutScheduleClient.ts`.
- **Tests:**
  `nexgent/adk_agents/ansimk_scout_agent/tests/unit/test_models.py`,
  `nexgent/adk_agents/ansimk_scout_agent/tests/unit/test_agent.py`,
  `nexgent/adk_agents/ansimk_scout_agent/tests/unit/test_run_service.py`,
  `nexgent/adk_agents/ansimk_scout_agent/tests/contract/test_api.py`,
  `scheduling-agent-poc/scheduling-agent/tests/unit/test_scout_schedule_models.py`,
  `scheduling-agent-poc/scheduling-agent/tests/unit/test_scout_schedule_repository.py`,
  `scheduling-agent-poc/scheduling-agent/tests/unit/test_scout_schedule_service.py`,
  `scheduling-agent-poc/scheduling-agent/tests/integration/test_scout_schedule_api.py`,
  `nexgent/frontend/src/features/agents/ScoutWorkbenchPage.test.tsx`,
  `nexgent/frontend/src/shared/api/scoutClient.test.ts`, and
  `nexgent/frontend/src/shared/api/scoutScheduleClient.test.ts`.
- **Documentation:**
  `nexgent/adk_agents/ansimk_scout_agent/README.md`,
  `nexgent/adk_agents/ansimk_scout_agent/.agents-cli-spec.md`,
  `nexgent/adk_agents/ansimk_scout_agent/docs/standalone-scout-agent-backend-poc.md`,
  `nexgent/adk_agents/ansimk_scout_agent/docs/scout-scheduling-integration.md`,
  and `nexgent/docs/08-implementation/ansimk-scout-agent-frontend-poc.md`.

## Validation

Latest relevant recorded validation:

- focused Scout backend: **27 passed**;
- full Scout backend: **49 passed**;
- focused scheduler: **73 passed**;
- focused frontend: **65 passed**;
- full frontend at that implementation stage: **209 passed**;
- production frontend build: **passed**;
- Ruff lint/format for changed Python files: **passed**; and
- `git diff --check`: **passed**.

Broader scheduler validation reached **100 passing tests**. One unrelated live
model test failed against an inert test endpoint, and three server E2E tests
could not bind already-occupied port 8000. These were environmental failures
and were not caused by the Additional Research Instructions implementation.

## Runtime Verification

After implementation, `nexgent-scout.service` and
`nexgent-scout-scheduler.service` were restarted successfully; both were
active/running.

Recurring Schedule ID `576a9ddb-55b8-47a5-8713-f723676dabc7` successfully
persisted and executed with:

> Focus on government prevention policies.

This verifies propagation of Additional Research Instructions through the
scheduled execution path.

# Final Status

| Requirement | Status | Handoff |
| --- | --- | --- |
| Recurring Scheduling | Completed | No known implementation work remaining |
| Summary/Key Findings Source Validation | Not implemented | Implement agreed semantic grounding design |
| Additional Research Instructions | Completed | No known implementation work remaining |
