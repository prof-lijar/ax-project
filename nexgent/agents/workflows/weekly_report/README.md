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
basic information, a warm LLM-authored one-paragraph `한주 총평`, metric
sections, then up to three detailed action
cards with approved descriptions, tags, and template IDs. Sleep and dispatch
are excluded from the entire report, including
the LLM fact package, narrative, Markdown, observations, and suggestions. The
activity signals are split into the unnumbered sibling sections `생활 활동` and
`생활 패턴`, each with its own flat `지표` list. The remaining sections are
indoor environment, device-data reception, and risk management; all five main
detail headings are unnumbered. The basic information
omits the score-band legend. The exclusive period end is displayed as the
inclusive Sunday. The approved year-round ranges include their boundaries:
`15℃ ≤ daily maximum temperature ≤ 31℃` and
`30% ≤ daily maximum humidity ≤ 70%`. Daily rows are collapsed by date across
devices, and Python uses the highest stored maximum on each date to count
temperature, humidity, combined, and directional departures. Zero or one
departure day is `GOOD`. Two or three repeated directional departure days are
`CAUTION`; four or more are `RISK`. A combined variant requires both stated
directional counters to meet its threshold; aggregate departures do not infer
a combined direction. The cool-humid CAUTION pair uses daily maximum
temperature below 18℃, while the cold-humid RISK pair counts daily maximum
humidity at or above 70%. The renderer shows uppercase status, exact approved copy,
summary, counts, and extrema. The numeric ranges remain internal evaluation
rules and are neither rendered nor sent to the model. The
deterministic renderer also shows the rounded current-week average risk score
and the approved uppercase status: `76–100 GOOD`, `26–75 CAUTION`, and
`0–25 RISK`. It renders the matching product-approved Korean guidance. The
score, status, and guidance stay outside model-authored prose. Fields without
approved source semantics,
including signal-loss counts and management-note details, are omitted rather
than inferred or rendered as empty placeholder sections.

The `생활 활동` and `생활 패턴` sections sum the raw `movement_count` and
`remote_control_count` columns respectively for each seven-day period and
evaluate each signal independently from
the current-to-previous total percentage. It renders `GOOD` for 70% up to but
not including 150%, `CAUTION` for 40% up to 70% or 150% through 250%, and
`RISK` below 40% or above 250%, using the
approved boundary inclusivity and Korean guidance. Exactly 250% is `CAUTION`;
missing totals or a zero previous total produce an unavailable comparison.

The device-data reception section evaluates the approved count columns on each
raw device-day row. Rows whose temperature, humidity, light, and movement
counts are all non-null and non-zero are good; remote-control count does not
participate in GOOD classification. A row whose temperature, humidity, and
light counts are all null is a power occurrence regardless of its activity
values. After excluding good and power, at least two of all five values in
0–10 is a position occurrence. These row categories are mutually exclusive. Two repeated power or
position occurrences produce the matching `CAUTION` result with power-first
weekly precedence. Otherwise one or more good occurrences produce `GOOD`; good
occurrences do not need to equal every source row. Rows matching none of the
three row rules appear as the neutral `기타 수신 패턴` count and do not override
a matched weekly status. If rows exist but no weekly rule matches, the status
is `판정 불가` and no power-check guide is created. A zero-source week alone uses
the actionable description `기기 전원이 연결되어 있는지 확인해 주세요.` without
inventing a power-pattern count. Status, exact Korean copy, summary, and counts
are Python-owned.

## Narrative boundary

After calculation, Python creates report-facing weekly data containing the
subscriber name, overall qualitative result, deterministic `생활 활동`,
`생활 패턴`, `실내 환경`, and `기기 상태` results, qualitative risk
management, and approved guardian actions. It sends no raw rows, totals,
percentages, thresholds, dates, measurements, sleep or dispatch fields,
`summary_outline`, or prewritten activity-combination sentence.

Prompt version `weekly-korean-free-summary-v21` asks the model to author the
complete `한주 총평` body as one short, natural paragraph. The response is plain
text rather than JSON. Validation rejects titles, labels, Markdown, line
breaks, digits, `움직임`, `리모컨`, English status values, formal administrative
endings, excluded topics, unsupported claims, and omitted material
CAUTION/RISK areas. One corrected retry is allowed; failure uses a disclosed
deterministic fallback built from the same report-facing section results.

For compatibility, the first validated sentence is stored in
`WeeklyNarrative.headline` and the remainder in `analysis_text`. Observations
and model suggestions stay empty. The renderer rejoins the two fields with one
space, preserving the exact model-authored paragraph; deterministic guardian
action cards are rendered separately.
The deterministic detail heading is `기기 상태`; its GOOD, power-check, and
position-check descriptions and short summaries use the exact approved
guardian-facing copy.
When sensor values are unavailable, the model may describe only the supplied
data limitation and must not infer a lifestyle or health condition. No digits
are allowed in the summary. Practical checks stay grounded in supplied section
descriptions or approved actions.
The maintained example is
[`examples/human-good-report.md`](examples/human-good-report.md). Qualitative
section results and guardian actions enter the prompt; raw sensor rows, totals,
thresholds, and numeric comparisons do not. Urgent wording such as `빠른` or
`즉시` is rejected.

## Guardian action guides

Python selects product-approved guardian guides from activity decrease `RISK`,
activity increase `CAUTION`, directional indoor-environment
`CAUTION`, combined indoor-environment `RISK`, and device-reception `CAUTION`
results. Remote-control increase likewise selects an action only at `CAUTION`;
increase `RISK` does not reuse it. Each guide owns an internal condition,
displayed title, description, tag, and optional template ID. The condition is
used only for deterministic selection; the card renders the title,
description, tag, and supplied template ID. Zero-source reception takes
priority because it affects report
reliability. The deterministic priority is device problem, activity change,
environment, then general check-in. At most three guides are rendered. Approved guides take
the first action slots. Related practical guidance is integrated beside its
supporting finding in `한주 총평`. Model suggestions
do not fill unused rendered slots because they have no approved tag or template
ID. The model receives approved titles as qualitative suggestions but never
selects their status mapping, ordering, description, tag, or template ID.
When the weekly risk score is `GOOD`, no area has a CAUTION/RISK status, no
mapped issue guide exists, and no risk event was detected, the section renders
the deterministic `평소처럼 안부를 확인해 주세요` guide with the approved stable-week
description and tag. Its template ID remains null because none was supplied.
Zero-source device reception instead produces the deterministic
`기기 전원이 연결되어 있는지 확인해 주세요` guide.

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
