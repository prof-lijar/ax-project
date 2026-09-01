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

The product owner promoted the wording/rule chart at spreadsheet document
`1tOuquKA_QrsWfWI6JlVTQ2z_pS2C5O9j5r8u6ZEo6QM`, sheet `1395281680`, to the
versioned presentation policy on 2026-08-27. Database rows remain the source of
facts; the promoted sheet owns classification boundaries, display copy,
guardian-guide selection, and priority. `analysis_wardperiodreport` is still
not an authoritative input.

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
- Collapse environment rows by local date, using the highest stored maximum
  across devices for promoted-sheet affected-day classification. Preserve the
  lowest minimum and highest maximum separately for rendered weekly extrema.
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

Risk management renders only the verified detection and resolution counts.
There is no approved detailed-record source, so do not render a `위험 관리 기록`
subsection or an unavailable-detail placeholder.

## Approved activity interpretation

The product owner approved a versioned weekly-total activity presentation rule
on 2026-08-25. Evaluate `movement_count` and `remote_control_count`
independently using `current total / previous total * 100`:

- below 40%: `RISK` decrease;
- 40% inclusive to below 70%: `CAUTION` decrease;
- 70% inclusive to below 150%: `GOOD` stable;
- 150% inclusive to 250% inclusive: `CAUTION` increase;
- above 250%: `RISK` increase.

For movement in the `생활 활동` section, render these exact description and
summary pairs:

- `GOOD/stable`: `활동은 비슷한 수준으로 이어졌어요.` / `평소 수준`;
- `CAUTION/decrease`: `활동이 조금 줄어든 모습이에요.` / `조금 감소`;
- `CAUTION/increase`: `활동이 조금 늘어난 모습이에요.` / `조금 증가`;
- `RISK/decrease`: `활동이 많이 줄었어요. 안부를 한 번 확인해 주세요.` /
  `많이 감소`;
- `RISK/increase`:
  `활동이 많이 늘었어요. 생활에 달라진 점이 있는지 살펴봐 주세요.` /
  `많이 증가`.

For remote-control use in the `생활 패턴` section, render these exact
description and summary pairs:

- `GOOD/stable`: `TV 이용 등 일상적인 생활 패턴도 비슷하게 이어졌어요.` /
  `평소 수준`;
- `CAUTION/decrease`: `TV 이용 등 일상적인 생활 패턴이 조금 줄었어요.` /
  `조금 감소`;
- `CAUTION/increase`: `TV 이용 등 일상적인 생활 패턴이 조금 늘었어요.` /
  `조금 증가`;
- `RISK/decrease`:
  `TV 이용 등 일상적인 생활 패턴이 많이 줄었어요. 안부를 한 번 확인해 주세요.` /
  `많이 감소`;
- `RISK/increase`:
  `TV 이용 등 일상적인 생활 패턴이 많이 늘었어요. 최근 생활에 달라진 점이 있는지 살펴봐 주세요.` /
  `많이 증가`.

The supplied rules place exactly 150% in the increase-CAUTION band and exactly
250% in CAUTION; `RISK` starts only above 250%. When
either total is unavailable or the previous total is zero, render the status
and ratio as unavailable rather than dividing by zero or inferring a trend.

The activity status, direction, exact section description, and short summary
enter the LLM's validated weekly-data payload as two independent report
results. Python does not select or require a movement-plus-TV combination
sentence for `한주 총평`. The model decides how to connect the two results in
natural guardian-facing prose, while validation still requires any material
CAUTION/RISK activity change to be represented.

Render each signal's uppercase status, exact approved Korean guidance, short
summary, current and previous totals, and comparison percentage from
deterministic Python. The model may receive only the resulting qualitative
guidance, never the totals, percentage, or thresholds.

In Markdown, render movement as the sibling `생활 활동` section and
remote-control use as `생활 패턴`. Each section owns its own flat `지표` list in
this order: `지난 한 주`, `2주 전`, and `2주 전과 비교`. Do not render the old
numbered `활동량` wrapper or the `움직임 합계` and `리모컨 사용 합계` metric
group labels. All other main detail headings (`실내 환경`, `기기 상태`,
and `위험 관리`) are also unnumbered.

## Approved environment interpretation

The product owner promoted the spreadsheet presentation rule on 2026-08-27
and revised its exact guardian-facing copy and two combined-condition
boundaries on 2026-08-31. For each observed date, aggregate all device rows and
classify the date from `max_temperature` and `max_humidity`.

The ordinary year-round departure bands remain:

- high temperature: above 31℃;
- low temperature: below 15℃;
- high humidity: above 70%;
- low humidity: below 30%.

The combined rules additionally require two explicit counters:

- cool temperature: below 18℃, used only by `CAUTION 7`;
- humidity at or above 70%, used only by `RISK 7`.

Thus exact 15℃ and 31℃ remain inside the ordinary temperature band, and exact
30% and 70% remain inside the ordinary humidity-departure band. Exact 18℃ does
not count as cool, while exact 70% does count for the special cold-humid RISK
combination. The private source snapshot carries compatibility-safe
`cool_temperature_days` and `humidity_at_or_above_70_days` counters; older
snapshots without them fall back to the stricter ordinary directional counts.
Weekly extrema remain separate rendered values and do not drive the day-count
classification directly.

The supplied word `반복` means four or more qualifying dates. Match exact
directional counts in this precedence:

1. combined `RISK 5–8`: high/high, high/low, low/at-or-above-70, or low/low,
   with both stated counts at least four;
2. directional `RISK 1–4`: high temperature, low temperature, high humidity,
   or low humidity on at least four dates;
3. combined `CAUTION 5–8`: high/high, high/low, cool/high, or low/low, with
   both stated counts between two and three inclusive;
4. directional `CAUTION 1–4`: high temperature, low temperature, high
   humidity, or low humidity on at least two dates;
5. `GOOD 1`: zero or one date with an ordinary temperature or humidity
   departure.

When aggregate departure dates reveal an unlisted mixed-direction pattern,
retain the existing deterministic CAUTION fallback and select the most
frequent verified ordinary direction without escalating to RISK. Both daily
maxima must be available for a date to enter any environment counter. If no
complete date exists, render the status, counts, description, and summary as
unavailable.

Render these exact description/summary pairs:

- `GOOD 1`: `집 안 온도와 습도가 대체로 쾌적하게 유지됐어요.` / `쾌적`;
- `CAUTION 1`: `집 안이 조금 더운 날이 있었어요. 냉방이나 환기 상태를 한 번 살펴봐 주세요.` / `조금 더움`;
- `CAUTION 2`: `집 안이 조금 추운 날이 있었어요. 난방 상태를 한 번 확인해 주세요.` / `조금 추움`;
- `CAUTION 3`: `집 안이 습한 날이 있었어요. 제습이나 환기가 필요한지 살펴봐 주세요.` / `습함`;
- `CAUTION 4`: `집 안이 건조한 날이 있었어요. 너무 건조하지 않은지 한 번 살펴봐 주세요.` / `건조함`;
- `CAUTION 5`: `덥고 습한 날이 있었어요. 냉방과 환기가 잘 되고 있는지 함께 살펴봐 주세요.` / `덥고 습함`;
- `CAUTION 6`: `집 안이 덥고 건조한 날이 있었어요. 냉방 상태와 실내 습도를 함께 살펴봐 주세요.` / `덥고 건조함`;
- `CAUTION 7`: `집 안이 다소 서늘하고 습한 날이 있었어요. 난방과 환기 상태를 함께 살펴봐 주세요.` / `서늘하고 습함`;
- `CAUTION 8`: `집 안이 춥고 건조한 날이 있었어요. 난방 상태와 실내 습도를 함께 살펴봐 주세요.` / `춥고 건조함`;
- `RISK 1`: `집 안이 많이 더운 날이 여러 번 이어졌어요. 냉방이 잘 되고 있는지 조금 더 세심하게 살펴봐 주세요.` / `더운 날 이어짐`;
- `RISK 2`: `집 안이 추운 날이 여러 번 이어졌어요. 난방 상태와 생활에 불편함은 없는지 살펴봐 주세요.` / `추운 날 이어짐`;
- `RISK 3`: `습한 날이 여러 번 이어졌어요. 제습이나 환기가 잘 되고 있는지 살펴봐 주세요.` / `습한 날 이어짐`;
- `RISK 4`: `건조한 날이 여러 번 이어졌어요. 집 안이 너무 건조하지 않은지 살펴봐 주세요.` / `건조한 날 이어짐`;
- `RISK 5`: `덥고 습한 날이 여러 번 이어졌어요. 냉방과 환기가 잘 되고 있는지 조금 더 세심하게 살펴봐 주세요.` / `덥고 습한 날 이어짐`;
- `RISK 6`: `덥고 건조한 날이 여러 번 이어졌어요. 냉방 상태와 실내 습도를 함께 살펴봐 주세요.` / `덥고 건조한 날 이어짐`;
- `RISK 7`: `춥고 습한 날이 여러 번 이어졌어요. 난방과 환기 상태를 함께 살펴봐 주세요.` / `춥고 습한 날 이어짐`;
- `RISK 8`: `춥고 건조한 날이 여러 번 이어졌어요. 난방 상태와 실내 습도를 조금 더 세심하게 살펴봐 주세요.` / `춥고 건조한 날 이어짐`.

Python renders the uppercase status, exact copy, summary, affected-day counts,
and weekly extrema. Numeric ranges remain internal and are not sent to the
model; only qualitative findings may enter the fact package.

## Approved device-status interpretation

The product owner approved a versioned device-reception presentation rule on
2026-08-25, revised its GOOD and power inputs on 2026-08-27, and revised the
section title and exact copy on 2026-08-31. Render the section heading as
`기기 상태`. For every
`analysis_devicedailysummary` row, inspect
`temperature_count`, `humidity_count`, `light_count`, `remote_control_count`,
and `movement_count` together:

- `device_good`: `temperature_count`, `humidity_count`, `light_count`, and
  `movement_count` are all non-null and non-zero; `remote_control_count` does
  not participate in GOOD classification;
- `device_power`: `temperature_count`, `humidity_count`, and `light_count` are
  all null; remote-control and movement values do not participate in power
  classification;
- `device_position`: after excluding both `device_good` and `device_power`, at
  least two of the five values are numeric and inside 0–10 inclusive.

Classify each row through the mutually exclusive `device_good`, `device_power`,
then `device_position` if/else-if order and count occurrences across the current
week. At weekly status selection, at least two power occurrences select
`CAUTION/device_power`; otherwise at least two position occurrences select
`CAUTION/device_position`; otherwise at least one good occurrence selects
`GOOD/device_good`. Good occurrences do not need to equal every source row.
Rows matching none of the three row rules are shown as a neutral derived
`기타 수신 패턴` count and do not override a matched weekly status. If source
rows exist but no weekly rule matches, label the result `판정 불가` without
claiming no reception or recommending a power check. Zero source rows remain
unavailable; absence of rows is not converted into a power or position event.
The deterministic detail description for a zero-source week is
`기기 전원이 연결되어 있는지 확인해 주세요.`; its occurrence counts remain
unavailable and it does not enter model-authored insights as a verified power
event.

Render these exact description/summary pairs:

- `GOOD/device_good`: `생활 정보가 빠짐없이 잘 들어왔어요.` / `정상`;
- `CAUTION/device_power`:
  `생활 정보가 들어오지 않은 날이 있었어요. 기기 전원이 잘 연결되어 있는지 확인해 주세요.` /
  `전원 확인`;
- `CAUTION/device_position`:
  `일부 생활 정보가 평소보다 적게 들어온 날이 있었어요. 기기가 제자리에 있는지 확인해 주세요.` /
  `위치 확인`.

Render the uppercase status, exact approved Korean description, short summary,
the three classified occurrence counts, and the derived other-pattern count in
deterministic Python. Raw row values and thresholds must not enter the model
fact package. A selected weekly power or position occurrence count may enter
the Python-owned summary outline as a significant value; narrative validation
permits only numeric tokens already present in that outline.

## Approved risk-score interpretation

The product owner approved a versioned weekly-average presentation rule on
2026-08-24, revised its status output on 2026-08-25, and revised the Korean
guidance on 2026-08-31.
Average the current week's non-null `risk_score` values, round the result to the
nearest whole point using half-up rounding, and render these bands:

- 76–100: `GOOD` and
  `전반적으로 평소와 비슷한 생활 흐름을 이어가셨어요.`;
- 26–75: `CAUTION` and
  `평소와 조금 다른 생활 모습이 보여요. 한 번 더 살펴봐 주세요.`;
- 0–25: `RISK` and
  `평소와 다른 생활 모습이 크게 보여요. 안부를 조금 더 세심하게 확인해 주세요.`.

Render the rounded score, uppercase status, and Korean band description from
deterministic Python without the full range legend. When no score exists or a
source value is outside 0–100, disclose that both score and status are
unavailable. Do not send the numeric score or its band to the model, and do not
treat the band as a diagnosis or certainty that an incident occurred.

## Approved guardian-action interpretation

The product owner promoted the spreadsheet guardian action guides on 2026-08-27
and replaced their copy, eligibility, tags, and template identifiers on
2026-08-31. Select only these deterministic mappings from validated statuses:

- movement `RISK/decrease`: `활동 감소` /
  `안부를 한 번 확인해 주세요` / `활동이 많이 줄어든 모습이에요.` /
  `안부 전화하기` / `ACT_RISK_01`;
- movement `CAUTION/increase`: `활동 증가` /
  `생활에 달라진 점이 있는지 살펴봐 주세요` /
  `활동이 평소보다 많이 늘어난 모습이에요.` / `생활 확인하기` /
  `ACT_RISK_02`;
- remote-control `RISK/decrease`: `생활 패턴 감소` /
  `안부를 한 번 확인해 주세요` /
  `TV 이용 등 일상적인 생활 패턴이 많이 줄었어요.` / `안부 전화하기` /
  `ACT_RISK_03`;
- remote-control `CAUTION/increase`: `생활 패턴 증가` /
  `최근 생활에 달라진 점이 있는지 살펴봐 주세요` /
  `TV 이용 등 일상적인 생활 패턴이 많이 늘었어요.` / `생활 확인하기` /
  `ACT_RISK_04`;
- environment `CAUTION 1`: `더운 환경` /
  `냉방이나 환기 상태를 확인해 주세요` / `집 안이 조금 더운 날이 있었어요.` /
  `환경 확인하기` / `ENV_CAUTION_01`;
- environment `CAUTION 2`: `추운 환경` / `난방 상태를 확인해 주세요` /
  `집 안이 조금 추운 날이 있었어요.` / `환경 확인하기` /
  `ENV_CAUTION_02`;
- environment `CAUTION 3`: `습한 환경` /
  `제습이나 환기가 필요한지 살펴봐 주세요` / `집 안이 습한 날이 있었어요.` /
  `환경 확인하기` / `ENV_CAUTION_03`;
- environment `CAUTION 4`: `건조한 환경` /
  `실내가 너무 건조하지 않은지 살펴봐 주세요` /
  `집 안이 건조한 날이 있었어요.` / `환경 확인하기` /
  `ENV_CAUTION_04`;
- environment `RISK 5`: `덥고 습한 환경` /
  `냉방과 환기 상태를 함께 확인해 주세요` /
  `덥고 습한 날이 여러 번 이어졌어요.` / `환경 확인하기` /
  `ENV_RISK_05`;
- environment `RISK 6`: `덥고 건조한 환경` /
  `냉방 상태와 실내 습도를 함께 확인해 주세요` /
  `덥고 건조한 날이 여러 번 이어졌어요.` / `환경 확인하기` /
  `ENV_RISK_06`;
- environment `RISK 7`: `춥고 습한 환경` /
  `난방과 환기 상태를 함께 확인해 주세요` /
  `춥고 습한 날이 여러 번 이어졌어요.` / `환경 확인하기` /
  `ENV_RISK_07`;
- environment `RISK 8`: `춥고 건조한 환경` /
  `난방 상태와 실내 습도를 함께 확인해 주세요` /
  `춥고 건조한 날이 여러 번 이어졌어요.` / `환경 확인하기` /
  `ENV_RISK_08`;
- device `CAUTION/power`: `전원 확인` /
  `기기 전원이 잘 연결되어 있는지 확인해 주세요` /
  `생활 정보가 들어오지 않은 날이 있었어요.` / `기기 확인하기` /
  `DEV_POWER_01`;
- device `CAUTION/position`: `위치 확인` /
  `기기가 제자리에 있는지 확인해 주세요` /
  `생활 정보가 평소보다 적게 들어온 날이 있었어요.` / `기기 확인하기` /
  `DEV_POS_01`.

The stable guide requires a GOOD weekly risk score, no mapped CAUTION/RISK
guide, no CAUTION/RISK activity, environment, or device status, and zero
detected risk events. It renders `상태 양호` /
`평소처럼 안부를 확인해 주세요` /
`평소와 비슷한 생활 흐름이 이어지고 있어요.` / `안부 전화하기`. No stable
template ID was supplied, so its validated `template_id` is null and the
Markdown omits that line. Preserve the existing zero-source power-check guide
as a data-availability safeguard; its template ID is also null because no ID
was supplied.

Render device problems first, then activity changes, environment, and the
general stable guide, with at most three guides. Increase `RISK` does not reuse
the increase `CAUTION` action. Model suggestions do not fill unused rendered
slots because they do not own approved tags or template IDs. Approved guide
titles may enter the prompt's
allowlisted suggested-actions field, but selection, ordering, condition, title,
description, tag, template ID, and rendered copy remain Python-owned. The
internal condition is not rendered; each card shows title, description, tag,
and its template ID when one was supplied.

## Approved weekly-summary interpretation

Prompt version `weekly-korean-free-summary-v27` extends the earlier
Python-owned summary formula and semantic outline. The LLM receives subscriber
identity as a summary-opening field plus the deterministic report-facing result
for `생활 활동`, `생활 패턴`, `실내 환경`, `기기 상태`, and
approved guardian actions. It does not receive raw rows, totals, ratios,
thresholds, dates, measurements, sleep or dispatch values, `summary_outline`,
raw risk-management data, `기본 정보`, overall score-band results, or a
prewritten activity-combination block.

The model authors the complete `한주 총평` as one short paragraph. It opens
with `지난 한 주 [이름]님은`, summarizes activity and everyday lifestyle
pattern in that first sentence, then connects indoor environment, device
status, and a grounded close like an experienced guardian-support adviser
rather than listing field names. Missing or incomparable data is not an abnormal result.
The output must not invent causes, diagnoses, risks, or actions. Related
findings are synthesized, same-purpose actions appear once, and sparse evidence
must not be padded with reassurance. Overall status and device reception are
not safety findings. Risk management and separate records are omitted from the
prompt and summary in every case; their deterministic detail section is not
changed.

The persona is an experienced customer-support adviser reporting the week of a
parent who lives alone to an adult child who cannot check in person. Use
`활동` and `TV 이용 등 일상적인 생활 패턴`, never `TV 이용 시간`. Put all
observations first and consolidate practical guardian checks in the final
sentence. Reject emotional-attitude directions such as `다정하게` and facts
added after an action request.

Normal summaries contain two to four sentences. Reject a section-by-section
recital of short single-fact sentences. Related GOOD activity/pattern findings
share the opening sentence, while GOOD device/environment findings share a
following sentence. The summary-only display name normalizes an underscore
immediately following a bracketed service label to a space; stored identity and
the rendered basic-information section remain unchanged.

The fixed `지난 한 주 [이름]님은` opening must not immediately repeat the
topic particle with `활동은`, `생활 활동은`, or `생활 패턴은`. Use an `이/가`
subject form in that first clause; later contrastive topic particles remain
available when grammatically useful. Prompt validation, correction, and the
deterministic fallback enforce the same rule.

The model returns body text only. Reject titles, labels, Markdown, lists,
line breaks, digits, `움직임`, `리모컨`, English status values, formal
administrative endings, excluded topics, rushed wording, and unsupported
interpretation. Every report area with a deterministic CAUTION/RISK result
remains mandatory. Repeated sentences,
repeated check-in intent, unsupported safety reassurance, and a generic stable
close that conflicts with an attention signal are also rejected. The summary
also rejects `위험`, alarm-amplifying words, and exclamation marks. Permit one
bounded corrective retry.

A usable supplied subscriber name is mandatory in the opening and replaces
generic subscriber honorifics in later direct references. For deterministic
complete lifestyle-information reception absence (`기기 상태: 자료 없음`), the
model receives only the subscriber plus neutral reception-absence and
power-check copy. Validation requires the approved two-sentence summary and
rejects overall lifestyle, activity, environment, or record interpretation.

For compatibility with the versioned `WeeklyNarrative` contract, Python splits
the validated first sentence into `headline` and the remaining sentences into
`analysis_text`; it does not rewrite either. The renderer joins them with one
space under `한주 총평`, preserving the model's single paragraph. Numeric and
status-rich detail sections and guardian action cards remain deterministic.

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
