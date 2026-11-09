# Weekly Report Activity Description Deduplication

Date: 2026-11-02 (Asia/Seoul)

## Implementation

`living_activity.descriptions` is composed from deterministic activity-policy
copy in `agents/workflows/weekly_report/domain/rendering.py`; the reporter LLM
prompt generates only the weekly summary. The fix therefore belongs in the
shared JSON/Markdown renderer rather than the summary prompt.

When both signals have the same `RISK` trend, keep each signal's observation
and retain the common action only in the second description. This handles
both identical check-in advice for decreases and equivalent change-checking
advice for increases (one version includes “최근”). Different actions, isolated
warnings, ordinary observations, and missing-data disclosures remain intact.
The underlying policy copy, summary prompt, metrics, tags, and schema stay
unchanged. No word-level deduplication is applied to Korean sentences.

Example for two large decreases:

```json
[
  "활동이 많이 줄었어요.",
  "TV 이용 등 일상적인 생활 패턴이 많이 줄었어요. 안부를 한 번 확인해 주세요."
]
```

## Validation and commands

Run from `agents/`:

```bash
.venv/bin/pytest tests/unit/test_weekly_report_rendering.py tests/unit/test_weekly_report_activity_policy.py tests/unit/test_weekly_report_graph.py
.venv/bin/ruff check workflows/weekly_report/domain/rendering.py tests/unit/test_weekly_report_rendering.py
```

Results: 71 tests passed; Ruff passed. Regression cases cover paired decreases,
paired increases, opposite trends, isolated guidance, and the user's stable /
slightly-increased example. Assertions check both JSON descriptions and the
Markdown activity section. Existing missing-data and policy tests also passed.
The test run reported pytest-asyncio deprecation warnings on Python 3.14.

## Operational scope and limitations

The fix applies when reports are newly rendered. No deployment, stored-report
rewrite, or export regeneration was performed. The implementation relies on
the approved policy format: the first sentence is the observation, followed
by action guidance for `RISK`. Future policy-copy changes should rerun these
tests and revisit this composition rule if the sentence structure changes.

Live source/LLM generation was not run because this is a deterministic rendering
change validated locally with synthetic inputs and a mocked graph model. An
optional live smoke check, with the existing source and model configuration
available, is (from `agents/`):

```bash
.venv/bin/python playground/weekly_report.py --week-start 2026-10-26
```

Inspect the living-activity section of a report where both signals have the
same large change. This command generates reports without storing them.
