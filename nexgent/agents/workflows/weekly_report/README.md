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
basic information, a warm `한주 총평` ending with a mode-aware deterministic
guardian action, numbered metric sections, then up to three detailed action
suggestions. Sleep and dispatch are excluded from the entire report, including
the LLM fact package, narrative, Markdown, observations, and suggestions. The
numbered sections are activity, indoor environment, device-data reception, and
risk management. The basic information
omits the score-band legend. The exclusive period end is displayed as the
inclusive Sunday. The approved year-round ranges are strict:
`15℃ < temperature < 31℃` and `30% < humidity < 70%`. Exact boundary values
are outside the recommended range. Daily rows are collapsed by date across
devices. Python uses all four stored extrema to count temperature, humidity, and combined recommended-range
departures. Zero or one combined departure day is `GOOD`. Two or three combined
departure days are `CAUTION` when both dimensions contribute; otherwise two or
more temperature-only or humidity-only departure days remain `CAUTION` unless
a RISK condition below applies. Directional `RISK` requires four or more dates
whose
daily maximum humidity is below 30% or above 70%, or whose daily maximum
temperature is below 15℃ or above 31℃. The boundaries are strict. Combined
temperature-and-humidity recommended-range departure on four or more dates is
`RISK 5`. The duplicated approved GOOD copy is mapped to zero and one departure
day respectively, and the otherwise unspecified `반복` boundary is normalized
to four days. The renderer shows uppercase status, exact approved copy,
summary, counts, and extrema. The numeric ranges remain internal evaluation
rules and are neither rendered nor sent to the model. The
deterministic renderer also shows the rounded current-week average risk score
and the approved uppercase status: `76–100 GOOD`, `26–75 CAUTION`, and
`0–25 RISK`. It renders the matching product-approved Korean guidance. The
score, status, and guidance stay outside model-authored prose. Fields without
approved source semantics,
including signal-loss counts and management-note details, are marked
unavailable rather than inferred.

The activity section sums the raw `movement_count` and `remote_control_count`
columns for each seven-day period and evaluates each signal independently from
the current-to-previous total percentage. It renders `GOOD` for 70–150%,
`CAUTION` for 40–70% or 150–250%, and `RISK` below 40% or above 250%, using the
approved boundary inclusivity and Korean guidance. Exactly 250% is `CAUTION`;
missing totals or a zero previous total produce an unavailable comparison.

The device-data reception section evaluates the five approved count columns on
each raw device-day row. Rows with all non-null, non-zero values are good; the
all-null measurement-count plus zero activity pattern is a power occurrence;
and, after excluding good and power, at least two values in 0–10 is a position
occurrence. These row categories are mutually exclusive. Two repeated power or
position occurrences produce the matching `CAUTION` result with power-first
weekly precedence. `GOOD` requires every available row to be good; unmatched
partial data and zero source rows remain unavailable. A zero-source week uses
the actionable description `기기 전원이 연결되어 있는지 확인해 주세요.` without
inventing a power-pattern count. Status, exact Korean copy, summary, and counts
are Python-owned.

## Narrative boundary

After calculation, Python converts numbers into an allowlisted qualitative
fact package, including deterministic activity and device-reception guidance.
The model receives qualitative section assessments and exact guardian-action
candidates, but no raw rows, notes, totals, percentages, or thresholds. It
writes a warm, calm Korean headline, analysis, observations,
and up to three gentle suggestions. Validation rejects invented digits,
malformed structure, categorical risk language, diagnoses, excessive
certainty, unrelated filler, and output outside the maximum length and sentence
bounds. Significant valid-day and device-issue counts are admitted
only when Python placed the exact numeric token in the outline.
One corrected retry is allowed; failure uses a disclosed deterministic grounded
fallback composed only from the supplied facts. A single complete
Markdown `json` code fence is normalized before strict validation because some
OpenAI-compatible models wrap otherwise valid JSON; surrounding prose and
malformed fences remain invalid.
Prompt version `weekly-korean-valuable-insights-v14` frames the model as a
Korean customer-support and guardian-communication expert and consumes a Python-owned
semantic outline with `ALL_GOOD`, `MIXED`, `RISK`, `LOW_DATA`, and
`PARTIAL_DEVICE` modes. The model reviews all available qualitative evidence,
then writes only one to four useful, connected insights; it is not required to
follow a fixed topic order or emit one sentence per area. Material CAUTION and
RISK topics remain mandatory, while GOOD areas are optional context.
When sensor values are unavailable, the outline describes the verified data
availability for activity, indoor environment, and device reception and links
missing reception to a power check without inferring a lifestyle or health
condition. Low and partial data are described only within the observable
range. Only outline-supplied significant day or
occurrence counts may be repeated; all other numbers remain prohibited. The
renderer still owns the deterministic CLOSE sentence. The personalized
headline starts with the report period `지난 한 주`, uses it exactly once in
the summary, and the final current-action sentence begins with `이번 주`.
Analysis starts with a connector back to the headline and varies its core
wording. Qualitative section assessments for movement, remote control, temperature,
humidity, and device reception plus exact guardian-action candidates enter the
prompt; raw sensor rows, totals, thresholds, and numeric comparisons do not.
If all three report areas are unavailable, analysis connects the activity
comparison limitation, indoor-environment limitation, and missing device
reception as useful grounded findings. Every analysis sentence requires a
natural connector, and urgent wording such as `빠른`
or `즉시` is rejected.
For absent reception, the deterministic CLOSE is
`이번 주에는 기기 전원 연결 상태를 확인해 주시고, 생활환경을 함께 살펴봐 주세요.`

## Guardian action guides

Python selects product-approved guardian guides from activity `RISK`, indoor
environment `RISK`, and device-reception `CAUTION` results. Each guide owns an
internal condition, a displayed title, and an analysis sentence. The condition
is used only for deterministic selection; the card renders the title and
analysis. Unavailable reception takes priority because it affects report
reliability; otherwise movement, remote control, environment, then device is
the deterministic order. At most three guides are rendered. Approved guides take
the first action slots. A separate summary policy combines at most two priority
checks into the deterministic `한주 총평` closing sentence. Validated model
suggestions fill only unused slots. The model receives approved titles as
qualitative suggestions but never selects their status mapping, ordering, or
analysis. The combined-environment source typo `롹인` is rendered as `확인`.
When all activity, environment, device-reception, and weekly score statuses are
explicitly `GOOD` and no risk event was detected, the section instead renders
the deterministic `꾸준히 안부를 확인해 주세요` guide with the approved stable-week
analysis. Unavailable data does not qualify for this GOOD fallback.
Unavailable device reception instead produces the deterministic
`기기 전원이 연결되어 있는지 확인해 주세요` guide. The summary CLOSE is not
passed into model suggestions, so it cannot reappear as a generic numbered
guardian action; the renderer also drops any invented time-scoped summary CLOSE
from numbered actions.

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

## Bulk export path

The compatibility graph above remains capped at twenty-five. For up to 10,000
reports, `workflows.weekly_report.bulk` uses the same source contracts,
calculation rules, reporter specialist, and renderer behind a durable worker.
A leased producer pages the source at one hundred wards per request; bounded
async consumers claim wards from PostgreSQL and write private atomic artifacts.
The final export is a seven-day ZIP with a manifest, JSONL records, and one
Markdown file per completed ward. Failed wards are recorded with safe error
codes and up to three attempts; one bad ward does not discard successful work.
Cancel requests are persisted and watched during execution. The worker cancels
in-flight model awaits, marks pending and leased items cancelled, and packages
only reports that completed before cancellation.

Every per-report narrative call has a bounded deadline controlled by
`WEEKLY_REPORT_ITEM_TIMEOUT_SECONDS` (60 seconds by default). A timed-out model
call becomes a deterministic template fallback, so one slow request cannot
hold the queue. Producer, consumer, or finalizer failures now persist a
terminal failed job and cancel unfinished items; the long-running worker logs
the safe failure and continues serving later jobs. ZIP downloads are emitted
in bounded chunks rather than being loaded into memory as one response, and
their `Content-Length` is the verified artifact size rather than zero.

This is intentionally not modeled as thousands of LangGraph subgraphs or
process-local agents. Independent work is distributed through durable leases,
so workers can restart or scale horizontally without duplicating completed
reports or growing graph state.

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
