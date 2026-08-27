# Weekly reporter source contract

## Authoritative sources

- `ansimk.analysis_devicedailysummary`: environment, activity, and sleep rows.
- `ansimk.analysis_wardevaluation`: risk events and scores.
- `ansimk.dispatch_dispatchrequest`: dispatch events and current resolution state.
- `ansimk.resources_ward`: ward identity.

Always schema-qualify these application-owned queries. The database also
contains `ansimk_clone` and `archive` relations with matching names; neither is
an approved weekly-report source, and PostgreSQL `search_path` must not select
the source implicitly.

Do not use spreadsheet columns or `analysis_wardperiodreport` as authoritative
for this implementation.

## Period and selection

- Current period: requested Monday inclusive to following Monday exclusive.
- Previous period: immediately preceding Monday inclusive to current Monday
  exclusive.
- Report-facing Korean labels call the current/reporting period `지난 한 주`,
  the previous/comparison period `2주 전`, and their ratio `2주 전과 비교`.
  They do not render `이번 주`, `지난주`, or `지난 주`.
- Default timezone: `Asia/Seoul`; accept valid IANA zones.
- Accept either unique explicit ward IDs or an opaque cursor, never both.
- Discover candidates from the union of current-period daily summaries,
  evaluations, and dispatches. Sort by ward ID. Interactive graph requests stay
  capped at twenty-five wards; durable bulk-source pages are capped at one
  hundred.
- Encode the last ward ID, week start, and timezone in an opaque cursor and
  reject a cursor used with a different period or timezone.

## Calculation semantics

- Count distinct daily dates for coverage and distinct device IDs for devices.
- Weight temperature, humidity, and light averages by their measurement counts.
- Use stored daily extrema for min/max and sum measurement counts.
- Collapse environment rows by local date, using the lowest stored minimum and
  highest stored maximum across devices before counting affected days.
- Arithmetic-average activity and night-awake values over non-null rows.
- Sum non-null `movement_count` and `remote_control_count` values separately
  for each week, and use those totals for the approved activity policy below.
- Evaluate device reception from each raw device-daily-summary row before
  weekly aggregation, using the approved policy below.
- Average clock times linearly to preserve existing service behavior.
- Count `DANGER` evaluations; count distinct local danger dates separately.
- Count `DANGER` to `STABLE` transitions, seeded by the final pre-period event.
- Average non-null risk scores, then apply the approved presentation policy below.
- Recompute both weeks from raw records.

Sleep and dispatch compatibility fields may remain inside the private source
contract during migration, but they are not reporting inputs. They must not
enter the LLM fact package, narrative, rendered Markdown, observations, or
guardian suggestions.

## Approved activity interpretation

The product owner approved a versioned weekly-total activity presentation rule
on 2026-08-25. Evaluate `movement_count` and `remote_control_count`
independently using `current total / previous total * 100`:

- below 40%: `RISK` decrease;
- 40% inclusive to below 70%: `CAUTION` decrease;
- 70% inclusive to 150% inclusive: `GOOD` stable;
- above 150% to 250% inclusive: `CAUTION` increase;
- above 250%: `RISK` increase.

The supplied rules leave exactly 250% uncovered (`CAUTION` is below 250%,
while `RISK` is above 250%). Keep the explicitly strict `RISK` boundary and
classify exactly 250% as `CAUTION` so every valid ratio has one status. When
either total is unavailable or the previous total is zero, render the status
and ratio as unavailable rather than dividing by zero or inferring a trend.

Render each signal's uppercase status, exact approved Korean guidance, short
summary, current and previous totals, and comparison percentage from
deterministic Python. The model may receive only the resulting qualitative
guidance, never the totals, percentage, or thresholds.

## Approved environment interpretation

The product owner revised the versioned presentation rule on 2026-08-26. Use
one strict year-round recommended range:

- temperature: `15℃ < value < 31℃`;
- humidity: `30% < value < 70%`.

For each observed date, aggregate all device rows and use `min_temperature`,
`max_temperature`, `min_humidity`, and `max_humidity`. A temperature day
departs when its minimum is less than or equal to 15℃ or its maximum is greater
than or equal to 31℃. A humidity day departs when its minimum is less than or
equal to 30% or its maximum is greater than or equal to 70%. The exact boundary
values are outside the recommended range. Count a combined departure date once
when either dimension departs.

The supplied word `반복` has no numeric boundary. Use four or more dates, which
matches the explicit combined `RISK` rule. Resolve the duplicated `GOOD` copy
deterministically: zero combined departure days selects variant 1 and one day
selects variant 2. Apply the following precedence:

1. `RISK 5` when both temperature and humidity contributed and combined
   departures occurred on four or more dates;
2. `RISK 1` when daily maximum humidity is below 30%, `RISK 2` when daily
   maximum humidity is above 70%, `RISK 3` when daily maximum temperature is
   below 15℃, or `RISK 4` when daily maximum temperature is above 31℃, when
   the same condition occurred on four or more dates. The boundaries are
   strict: exactly 30%, 70%, 15℃, or 31℃ is not an extreme RISK day;
3. `CAUTION 3` when both dimensions contributed across two or three combined
   departure dates;
4. `CAUTION 1` for at least two humidity departure dates or `CAUTION 2` for at
   least two temperature departure dates;
5. `GOOD 1` for zero combined departure dates or `GOOD 2` for one.

All four daily extrema must be available for a date to enter these counts. If
no complete date exists, render the status, counts, description, and summary as
unavailable. Python renders the uppercase status, exact approved Korean copy,
short summary, affected-day counts, and weekly extrema. The numeric recommended
ranges are internal evaluation rules and are not rendered or sent to the model.
Only the qualitative description may enter the model fact package.

## Approved device-reception interpretation

The product owner approved a versioned device-reception presentation rule on
2026-08-25. For every `analysis_devicedailysummary` row, inspect
`temperature_count`, `humidity_count`, `light_count`, `remote_control_count`,
and `movement_count` together:

- `device_good`: all five values are non-null and non-zero;
- `device_power`: the three measurement-count values are null and both remote
  control and movement are zero;
- `device_position`: after excluding both `device_good` and `device_power`, at
  least two of the five values are numeric and inside 0–10 inclusive.

Classify each row through the mutually exclusive `device_good`, `device_power`,
then `device_position` if/else-if order and count occurrences across the current
week. At weekly status selection, at least two power occurrences select
`CAUTION/device_power`; otherwise at least two position occurrences select
`CAUTION/device_position`. Select `GOOD/device_good` only when at least one
source row exists and every source row is good. A partial combination that
matches neither weekly rule remains unavailable rather than claiming that all
data was normal. Zero source rows remain unavailable; absence of rows is not
converted into a power or position event. The deterministic detail description
for a zero-source week is `기기 전원이 연결되어 있는지 확인해 주세요.`; its
occurrence counts remain unavailable and it does not enter model-authored
insights as a verified power event.

Render the uppercase status, exact approved Korean description, short summary,
and the three occurrence counts in deterministic Python. Raw row values and
thresholds must not enter the model fact package. A selected weekly power or
position occurrence count may enter the Python-owned summary outline as a
significant value; narrative validation permits only numeric tokens already
present in that outline.

## Approved risk-score interpretation

The product owner approved a versioned weekly-average presentation rule on
2026-08-24 and revised its status output and Korean guidance on 2026-08-25.
Average the current week's non-null `risk_score` values, round the result to the
nearest whole point using half-up rounding, and render these bands:

- 76–100: `GOOD` and `지난 한 주는 대체로 안정적인 상태가 유지됐어요.`;
- 26–75: `CAUTION` and
  `지난 한 주는 평소와 다른 흐름이 일부 확인됐어요.`;
- 0–25: `RISK` and
  `지난 한 주는 즉시 확인이 필요한 위험 신호가 확인됐어요.`.

Render the rounded score, uppercase status, and Korean band description from
deterministic Python without the full range legend. When no score exists or a
source value is outside 0–100, disclose that both score and status are
unavailable. Do not send the numeric score or its band to the model, and do not
treat the band as a diagnosis or certainty that an incident occurred.

## Approved guardian-action interpretation

The product owner approved deterministic guardian action guides on 2026-08-25.
Select them only from the already-validated activity, environment, and device
statuses:

- movement `RISK/decrease`: `움직임 감소` / `안부 확인이 필요해요` /
  `움직임이 많이 줄었어요.`;
- movement `RISK/increase`: `움직임 증가` /
  `생활 변화를 확인해 주세요` / `움직임이 평소보다 크게 늘었어요.`;
- remote-control `RISK/decrease`: `리모컨 감소` / `생활 확인이 필요해요` /
  `리모컨 사용이 많이 줄었어요.`;
- remote-control `RISK/increase`: `리모컨 증가` / `안부 전화를 권해요` /
  `리모컨 사용이 반복적으로 많았어요.`;
- environment `RISK`: map dry, humid, hot, cold, and combined departures to
  their approved internal condition, displayed title, and analysis by semantic
  condition rather than reusing internal variant numbering;
- device `CAUTION/power`: `전원뽑음 주의` / `전원 확인이 필요해요` /
  `기기 전원이 빠진 이력이 있어요.`;
- device `CAUTION/position`: `기기위치변경 주의` /
  `기기 위치 확인이 필요해요` /
  `움직임·리모컨 사용이 적게 확인됐어요.`;
- device reception unavailable: `센서 자료 부족` /
  `기기 전원이 연결되어 있는지 확인해 주세요` /
  `지난 한 주 기기 데이터 수신이 확인되지 않았어요.`;
- all activity, environment, device-reception, and weekly score statuses `GOOD`
  with zero detected risk events: `상태 양호` /
  `꾸준히 안부를 확인해 주세요` /
  `지난 한 주는 큰 이상 없이 안정적인 흐름을 보였어요.`.

Render an unavailable-reception power check first when applicable; otherwise
use movement, remote control, environment, then device order, with at most
three guides. When none applies, use the stable GOOD guide only if
every status above is explicitly GOOD and no risk event was detected;
unavailable data never qualifies. Deterministic guides occupy the first slots;
validated model suggestions may fill unused slots. The first deterministic
title also closes `한주 총평`. The supplied `롹인` typo is normalized to `확인`
in the combined-environment title. Guide titles may enter the prompt's
allowlisted suggested-actions field, but selection, ordering, internal
conditions, displayed titles, analyses, and rendered copy remain Python-owned.
The internal condition is not rendered; each card displays the second-column
title and third-column analysis only.

## Approved weekly-summary interpretation

The product owner approved a structured `한주 총평` policy on 2026-08-25.
Treat the current snapshot's `covered_days` as `valid_days`; the current source
does not expose a separate `data_quality_code`, so derive it deterministically:

- fewer than four valid days: `LOW_DATA`;
- otherwise, device-power CAUTION: `PARTIAL_POWER`;
- otherwise, device-position CAUTION: `PARTIAL_POSITION`;
- otherwise: `VALID`.

Select summary mode in this precedence: `LOW_DATA`, `PARTIAL_DEVICE`, `RISK`,
`ALL_GOOD`, then `MIXED`. Partial-device mode takes precedence over a derived
activity risk because incomplete reception can distort the weekly comparison.
Python builds one semantic evidence outline containing:

- INTRO/headline: data limitation first for low or partial data; otherwise the
  overall GOOD-versus-issue contrast;
- activity: evaluatable movement and remote-control evidence, or their verified
  comparison-data limitation;
- environment: evaluatable temperature and humidity evidence, or the verified
  observation limitation;
- device: evaluatable device-reliability evidence, or missing reception linked
  to the approved power check;
- CLOSE: at most two integrated guardian actions, with an actual-wellbeing
  check as the default.

The reporter reviews all supplied evidence and selects valuable weekly insights
for the narrative. Every CAUTION or RISK issue is required; GOOD areas are
optional context. Python-supplied data-availability findings must be connected
naturally rather than replaced by a generic inability-to-summarize message. In
`LOW_DATA` and `PARTIAL_DEVICE`, wording stays within the observable range and
must not convert missing reception into a safety or health conclusion. The
headline alone starts with and contains `지난 한 주`; every analysis sentence
uses a natural connector and varies the headline wording. Urgent wording is
forbidden. The deterministic CLOSE starts with `이번 주`; it is not a model
suggestion and cannot be rendered as a numbered guardian action.
For absent reception, the exact CLOSE is
`이번 주에는 기기 전원 연결 상태를 확인해 주시고, 생활환경을 함께 살펴봐 주세요.`
Only significant values pre-rendered by Python may appear in the narrative:
valid-day count and selected device-issue occurrence count.
Activity totals, averages, ratios, thresholds, and raw measurements remain
excluded.

The first summary sentence is Python-owned and personalized with the validated
ward display name plus one non-duplicated `님` honorific. The renderer uses this
outline headline directly. The model receives separate qualitative assessments
for `movement_count`, `remote_control_count`, temperature, humidity, and device
data plus exact deterministic guardian-action candidates. It may select a
candidate title for suggestions but may not receive raw rows, calculate
thresholds, change status mapping, or rewrite candidate title and analysis.

## API and security

Use `POST /internal/v1/weekly-report/source` with `WeeklyReportRequest` and
`WeeklyReportSourceResponse`. Keep the service on the private application
network and require parameterized application-owned SQL, pooled read-only
transactions, bounded timeouts, safe errors, and readiness checks. Never expose
a generic query endpoint.

For durable bulk execution, any producer, consumer, or finalizer exception must
persist a terminal job state and cancel unfinished items so an oldest failed
job cannot block later jobs. Bound each narrative model await with
`WEEKLY_REPORT_ITEM_TIMEOUT_SECONDS`; use the deterministic grounded fallback
for a timed-out item and continue the batch. Send verified ZIP artifacts in
bounded chunks and advertise the verified artifact byte size as
`Content-Length`; never initialize a streamed ZIP with a zero-length response
header.
