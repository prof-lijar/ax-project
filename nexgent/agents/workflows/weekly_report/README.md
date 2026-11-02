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

The source service reads schema-qualified raw tables from `ansimk`:

- `ansimk.analysis_devicedailysummary` for environment, activity, and sleep;
- `ansimk.analysis_wardevaluation` for risk events, danger days, score averages, and
  `DANGER` to `STABLE` transitions;
- `ansimk.dispatch_dispatchrequest` for requests and unresolved requests;
- `ansimk.resources_ward` for ward identity.

Matching raw source tables under `ansimk_clone` and `archive` are deliberately excluded.
For previous motion and remote-control totals only, the service reads the
preceding saved report from local `archive.resources_ward_weekly_report`.
The source database must contain the bulk writer's saved reports, and its role
needs SELECT on this table. Missing or invalid prior counts are unavailable,
with a source warning and no recalculation fallback. Production-only manual
corrections must also be reflected in the local baseline to carry forward.
The connection remains configured by `ANSIMK_DATABASE_DSN`; changing its
database name or PostgreSQL `search_path` is not required. Production delivery
and coverage queries continue to use the production `ansimk` schema.

Python owns all arithmetic. Environment averages are measurement-count
weighted, activity averages are arithmetic means, and clock times use the
existing linear averaging behavior. Both periods are half-open Monday ranges
in the requested IANA timezone.

Every validated report carries two equivalent presentation outputs. The
legacy `markdown` field is retained. The frontend-ready
`template_data` field is a strict, versioned JSON object with stable section
keys: `basic_info`, `weekly_summary`, `living_activity`, `indoor_environment`,
`device_status`, `risk_management`, and
`guardian_actions`. Numeric metrics include both their raw value and approved
Korean display value, so clients do not parse units or formatted prose.
Interactive generation remains non-writing. The durable bulk finalizer also
stores frontend `template_data` in PostgreSQL.

The rendered Markdown follows the guardian-facing `주간 생활 리포트` layout:
basic information, a warm LLM-authored one-paragraph `한주 총평`, metric
sections, then up to three detailed action cards with approved descriptions,
tags, and template IDs. Sleep and dispatch
are excluded from the entire report, including
the LLM fact package, narrative, Markdown, observations, and suggestions. The
activity signals share one unnumbered `생활 활동` section with the child
headings `활동감지` and `리모컨 이용`. Their descriptions are combined above the
children, and one `태그` reflects the worse signal status. The remaining
sections are indoor environment, device-data reception, and risk management.
When both activity signals have the same `RISK` trend, the combined descriptions
retain both observations and include their shared action only after the second
observation. This also combines the equivalent increase guidance with and
without “최근”. Different actions and single-signal guidance remain intact.
The basic information
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

The `활동감지` and `리모컨 이용` children sum the raw `movement_count` and
`remote_control_count` columns respectively for the current seven-day period.
Their previous totals are copied from the same ward's saved preceding report's
`current_week` fields. They evaluate each signal independently from
the current-to-previous total percentage. It renders `GOOD` for 70% up to but
not including 150%, `CAUTION` for 40% up to 70% or 150% through 250%, and
`RISK` below 40% or above 250%, using the
approved boundary inclusivity and Korean guidance. Exactly 250% is `CAUTION`;
missing totals or a zero previous total produce an unavailable comparison.

Missing indoor-environment values render as `-`. The section distinguishes
temperature-only, humidity-only, and combined data limitations with approved
copy. Missing count-based other/position display values render as `0`; their
structured raw values remain null and do not affect deterministic status
calculation.

The device-data reception section evaluates the approved count columns
on each raw device-day row. At least two numeric counts in 0–10 inclusive
form a position occurrence, including rows with all-positive counts. Check
position first, then power (null temperature, humidity, and light), then good
(non-null/non-zero temperature, humidity, light, and movement). Null values
do not count as low. These categories remain mutually exclusive.
Two repeated power or position occurrences produce the matching `CAUTION` result with power-first
weekly precedence. Otherwise one or more good occurrences produce `GOOD`; good
occurrences do not need to equal every source row. Rows matching none of the
three row rules appear as the neutral `기타 수신 패턴` count and do not override
a matched weekly status. If rows exist but no weekly rule matches, the status
is `판정 불가` and no power-check guide is created. A zero-source week alone uses
the actionable description `기기 전원이 연결되어 있는지 확인해 주세요.` without
inventing a power-pattern count. Status, exact Korean copy, tag, and displayed
metrics are Python-owned. `정보 수신` uses the current `자료가 있는 날` value;
`전원 확인` uses selected-period days minus that value. Both render in days.
The old power-pattern occurrence count remains internal to status selection and
is not rendered as this metric.

## Narrative boundary

After calculation, Python creates report-facing weekly data containing the
subscriber name for the summary opening, deterministic `생활 활동`,
`생활 패턴`, `실내 환경`, and `기기 상태` results, and approved guardian
actions. It sends no raw rows, totals,
percentages, thresholds, dates, measurements, sleep or dispatch fields,
`summary_outline`, risk-management data, report `기본 정보`, overall
score-band results, or prewritten activity-combination sentence.

Prompt version `weekly-korean-free-summary-v28` asks the model to author the
complete `한주 총평` body as one short, natural paragraph. The response is plain
text rather than JSON. Validation rejects titles, labels, Markdown, line
breaks, digits, `움직임`, `리모컨`, English status values, formal administrative
endings, excluded topics, unsupported claims, omitted material CAUTION/RISK
areas, repeated findings/actions, unsupported
safety reassurance, and attention summaries that end with contradictory
generic reassurance. It also rejects `위험`, rushed or alarm-amplifying words,
exclamation marks, persona-misaligned wording, actions before the final
sentence, and new facts after an action. One corrected retry is allowed; failure uses a disclosed
deterministic fallback built from the same report-facing section results.

The model synthesizes related section findings instead of copying their
descriptions in order and writes each same-purpose action once. Risk-management
and separate-record data are always omitted from the summary prompt and output;
the deterministic detail section remains available elsewhere in the report. Device
reception describes information availability, not the subscriber's health or
safety. Sparse data stays concise rather than being padded with reassuring
filler.

The summary voice is an experienced customer-support adviser explaining the
week of a parent who lives alone to an adult child living apart. It uses
`활동` and `TV 이용 등 일상적인 생활 패턴`, never `TV 이용 시간`, presents
all observations first, and puts consolidated practical checks in the final
sentence. Emotional-attitude directions such as `다정하게` are rejected.
The first sentence starts with `지난 한 주 [이름]님은` and carries the core
activity/lifestyle-pattern flow. Normal summaries use two to four sentences and
join related GOOD activity/pattern and device/environment findings instead of
reciting one short sentence per section. A summary-only service-label separator
such as `[넥스터]_이름` is presented as `[넥스터] 이름`; stored and rendered
basic information is unchanged.
Because the fixed opening already ends in `님은`, its first clause uses
`활동이` or `TV 이용 등 일상적인 생활 패턴이` instead of immediately
repeating `활동은` or `생활 패턴은`. Validation, correction, and fallback all
enforce this Korean-particle rule.

A known usable subscriber name must appear in the opening and replaces generic
honorifics in later references. When complete lifestyle-information reception
is absent and `기기 상태` is `자료 없음`, the model receives only the subscriber
and approved reception/power-check facts. The summary is limited to
`생활 정보가 들어오지 않은 날이 있었어요` followed by
`기기 전원이 잘 연결되어 있는지 확인해 주세요`; unrelated overall-state,
activity, environment, and record interpretation are prohibited.

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
`CAUTION` or `RISK`, combined indoor-environment `RISK`, and device-reception `CAUTION`
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
ID. The model receives approved titles as observation-style card headings, not
as closing action sentences, and never selects their status mapping, ordering,
description, tag, or template ID. Summary actions remain grounded in verified
section descriptions.
When the weekly risk score is `GOOD`, no area has a CAUTION/RISK status, no
mapped issue guide exists, and no risk event was detected, the section renders
the deterministic `평소와 비슷하게 지내셨어요` guide with the approved stable-week
description and tag. Its template ID is `GUI_GOOD_01`.
Zero-source device reception instead produces the deterministic
`기기 전원이 연결되어 있는지 확인해 주세요` guide.
If no card is selected at all, the empty-state message also outputs
`GUI_GOOD_01` through `template_id` in both JSON and Markdown.

All rendered detail sections use the label `태그`, not `요약`. In structured
template JSON, the indoor-environment and device-status objects expose `tag`
keys for the same values.

## Report storage

The approved table definition for JSON report persistence is available at
`source/migrations/004_create_archive_ward_weekly_report.sql`. It creates
`archive.resources_ward_weekly_report` with a foreign key to
`archive.resources_ward`, one row per ward/week start, queryable score and status
columns, and non-null JSONB `report_data`.

After all completed report artifacts and the ZIP export have been built, the
bulk worker uses a dedicated `WEEKLY_REPORT_STORAGE_DATABASE_DSN` to upsert
frontend `template_data`. It sends bounded batches inside one transaction and
uses `ON CONFLICT (ward_id, week_start_date) DO UPDATE`, so recovery replaces
the same week instead of creating duplicates. `week_end_date` is the inclusive
Sunday shown in the report; updates also advance `updated_at`. Interactive
generation and the private source API never use this writer. For compatibility,
the worker falls back to `ANSIMK_DATABASE_DSN` when the dedicated variable is
unset; production should configure the dedicated least-privilege role.

The scheduled migration reads local `archive.resources_ward_weekly_report`
and writes production `ansimk.resources_ward_weekly_report`. Production ward
checks and coverage queries stay in `ansimk`. The optional local sync outbox
remains `ansimk.weekly_report_sync_outbox` in the same local database; pending
deliveries are preserved and report/outbox writes still share one transaction.

On 2026-10-17, source reads returned to `ansimk` because archive daily summaries
contained partial-day snapshots despite seven-day row coverage. Rebuild/recreate
the source API between jobs. Local report storage remains in `archive`; every
source ward must also exist in `archive.resources_ward` for its storage foreign
key. The live roster check found no missing parents. Use fresh jobs after the
switch: staged snapshots and existing reports are not recalculated by changing
the source. Historical scheduler receipts still prevent automatic regeneration.
Affected weeks require deliberate regeneration and production migration.

The live read-only check on 2026-10-06 found that the currently configured
source role has SELECT but lacks INSERT and UPDATE on the archive report
table. Before deploying, configure `WEEKLY_REPORT_STORAGE_DATABASE_DSN` with
a writer role that has schema USAGE and SELECT/INSERT/UPDATE on that table
(plus sequence privileges if the table uses a serial default). The existing
archive table uses an identity column. No permissions were changed during
implementation.

## Input

```json
{
  "week_start": "2026-08-03",
  "timezone": "Asia/Seoul",
  "ward_ids": [101, 102],
  "limit": 25
}
```

`week_start` must be Monday. Omit `ward_ids` to discover every `resources_ward`
row, including wards without weekly records,
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
The worker admits up to four jobs concurrently by default, oldest first. Their
consumers share one process-wide concurrency ceiling, so later jobs begin
promptly without multiplying model-call capacity.
The final export is a seven-day ZIP with a manifest, JSONL records, one
unchanged `reports/<ward_id>.md` file, and one frontend-ready
`json/<ward_id>.json` template per completed ward. All selected wards must
complete before report storage or successful export registration. Failed wards
retain safe error codes and up to three attempts; completed artifacts remain
recoverable, but a smaller batch cannot be committed as successful.
Cancel requests are persisted and watched during execution. The worker cancels
in-flight model awaits, marks pending and leased items cancelled, and packages
only reports that completed before cancellation, without partial report-table
writes. The scheduled pipeline follows continuation jobs until every ward is
processed; its per-job limit does not cap weekly coverage.

Every per-report narrative call has a bounded deadline controlled by
`WEEKLY_REPORT_ITEM_TIMEOUT_SECONDS` (60 seconds by default). A timed-out model
call becomes a deterministic template fallback, so one slow request cannot
hold the queue. Model errors and invalid output also use fallback; a prose-policy
failure uses a fixed neutral summary with the validated detail sections.
Guardian reports contain no fallback-generation notice. Internal generation
metadata retains the mode and reason. Producer, consumer, or finalizer failures persist a
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

Operator recovery can skip reports rejected by NOT NULL constraints with
`--write --skip-not-null`; regular bulk finalization remains atomic. See
[recovery instructions](../../docs/weekly-report-database-recovery.md) for
counts, exit codes, and deployment commands.
