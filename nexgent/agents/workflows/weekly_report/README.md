# `ansimk_weekly_reporter`

This manually triggered LangGraph workflow produces grounded Korean weekly
reports for up to twenty-five wards. It preserves the registered graph ID and
the existing `danger_days` fields used by the frontend.

## Data flow

The private `apps.weekly_report_api` FastAPI process reads raw `ansimk` tables
through a reusable pooled `asyncpg` integration. It returns versioned current
and previous seven-day snapshots to the graph through a private-network HTTP
client. The graph never receives database credentials and exposes no arbitrary
SQL tool.

The source service reads schema-qualified tables only from `ansimk`:

- `ansimk.analysis_devicedailysummary` for environment, activity, and sleep;
- `ansimk.analysis_wardevaluation` for risk events, danger days, score averages, and
  `DANGER` to `STABLE` transitions;
- `ansimk.dispatch_dispatchrequest` for requests and unresolved requests;
- `ansimk.resources_ward` for ward identity.

Matching tables under `ansimk_clone` and `archive` are deliberately excluded.

Python owns all arithmetic. Environment averages are measurement-count
weighted, activity averages are arithmetic means, and clock times use the
existing linear averaging behavior. Both periods are half-open Monday ranges
in the requested IANA timezone.

The rendered Markdown follows the guardian-facing `주간 생활 리포트` layout:
basic information, a weekly summary, five numbered sections for sleep,
activity, environment, data reception, and risk management, then up to three
grounded action suggestions. The exclusive period end is displayed as the
inclusive Sunday. Fields without approved source semantics, including a
subscriber score, environmental recommendation thresholds, signal-loss
counts, and management-note details, are marked unavailable rather than
inferred.

## Narrative boundary

After calculation, Python converts numbers into an allowlisted qualitative
fact package. The model receives no raw rows, notes, descriptions, or numeric
values. It writes a warm, calm Korean headline, analysis, observations, and up
to three gentle suggestions. Validation rejects digits, malformed structure,
categorical risk language, diagnoses, excessive certainty, and output outside
the required length and sentence bounds. One corrected retry is allowed;
failure uses a disclosed deterministic warm fallback. A single complete
Markdown `json` code fence is normalized before strict validation because some
OpenAI-compatible models wrap otherwise valid JSON; surrounding prose and
malformed fences remain invalid.
Prompt version `weekly-korean-warm-v2` also requires explicit sentence-ending
punctuation and gives the one corrective retry a safe rule-specific message
instead of an opaque validation code.

## Input

```json
{
  "week_start": "2026-08-03",
  "timezone": "Asia/Seoul",
  "ward_ids": [101, 102],
  "limit": 25
}
```

`week_start` must be Monday. Omit `ward_ids` for automatic candidate discovery
and use `next_cursor` on a later manual request. `ward_ids` and `cursor` are
mutually exclusive.

Required source configuration is documented in `.env.example`. The FastAPI
service is private in Compose and performs read-only transactions. Scheduling
and rendered-report persistence remain outside this workflow.

## Slack delivery

`slack_delivery.py` is an explicit post-generation boundary for sending an
already validated batch through the shared `SlackService`. It uses the
approved default channel unless an operator selects a configured logical
destination such as `reports`, rejects arbitrary channel IDs, spaces multi-ward
messages, and requires human confirmation because reports contain care-related
information. It is intentionally not a graph node, so a LangGraph retry cannot
silently duplicate a Slack side effect. Setup and the manual end-to-end command
are documented in
`docs/slack-outbound-messaging.md`.
