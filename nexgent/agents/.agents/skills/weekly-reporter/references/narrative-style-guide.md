# Korean weekly narrative style

Use the product-owner-promoted spreadsheet wording tab for deterministic
section classifications, section copy, and guardian-action rules. Database
facts and all calculations still enter through validated Python contracts.

## Summary ownership

`한주 총평` is authored as a complete paragraph by the LLM. Python must not
select an exact activity-combination sentence, calculate a summary mode, or
assemble the normal LLM summary from formula-owned prose.

The LLM receives only report-facing, Python-verified weekly data:

- subscriber display name as summary identity only, not a `기본 정보` block;
- `생활 활동`, `생활 패턴`, `실내 환경`, and `기기 상태` status,
  description, and short summary;
- already-approved guardian-action titles.

Do not send raw rows, totals, ratios, thresholds, dates, sensor measurements,
management notes, risk-management data, sleep data, dispatch data, `summary_outline`,
`required_topics`, or Python-composed summary sentences to the LLM.

## Prompt and output

Prompt version `weekly-korean-free-summary-v28` extends the product-owner
system prompt with production feedback rules, then replaces
`{{WEEKLY_REPORT_DATA}}` with the validated JSON payload. The model returns
only the completed Korean summary body, not JSON and not separate headline,
observation, or suggestion fields.

The paragraph should:

- sound like an experienced customer-support adviser explaining the week of a
  parent who lives alone to an adult child who cannot check in person;
- open with `지난 한 주 [이름]님은` and put the core activity and everyday
  lifestyle-pattern flow in that first sentence;
- connect activity/pattern, indoor environment/device state, and a grounded
  close as one short story;
- synthesize related findings instead of copying each section description in
  sequence, mention each fact once, and consolidate same-purpose actions into
  one recommendation;
- stay concise when evidence is sparse rather than filling the paragraph with
  reassurance or repeated explanations;
- use respectful, natural `해요체`;
- avoid diagnostic, causal, rushed, categorical, or anxiety-amplifying claims;
- treat missing or incomparable data as a limitation, never an abnormal
  condition; and
- avoid inventing an action when no approved action exists, beyond asking the
  guardian to continue watching as usual.

Describe activity as `활동` and remote-control-derived evidence as `TV 이용 등
일상적인 생활 패턴`; never reinterpret a count as `TV 이용 시간`. State all
observations before a single final action sentence. Do not add a device-state
fact after asking the guardian to act, and do not direct an emotional manner
with `다정하게`, `따뜻하게`, or similar wording. Ask for a practical check-in
or device/environment check instead.

Guardian-card titles are observation-style headings, not necessarily action
requests. They may be supplied as qualitative context, but the summary's final
practical check must be grounded in the verified section descriptions. The
deterministic fallback likewise ignores card titles when selecting its closing
action.

For normal weekly data, use two to four sentences. Avoid a sequence of short,
single-fact sentences. Join related findings with natural Korean connective
endings such as `~했고`, `~지만`, and `~도`. When all four report areas are
GOOD, combine activity with everyday lifestyle pattern in the opening, and
combine device reception with indoor environment in the next sentence.

Because the fixed opening already ends in the topic particle `님은`, do not
begin its next phrase with another topic-marked noun such as `활동은` or `생활
패턴은`. Use `활동이` or `TV 이용 등 일상적인 생활 패턴이`, or restructure
the clause. A later `은/는` may be used only when it serves a real contrast.

When a usable subscriber display name is supplied, include it in the opening.
If the subscriber is named again later, repeat the actual name rather than
using `가입자님`, `대상자님`, `어르신`, or `고객님`.

When complete lifestyle-information reception is absent and deterministic
`기기 상태` is `자료 없음`, send the model only the subscriber, the reception
absence marker, and the approved power check. Do not send or summarize overall
score-band, activity, environment, or record results for this case. The summary
contains exactly two grounded ideas: `생활 정보가 들어오지 않은 날이 있었어요`
and `기기 전원이 잘 연결되어 있는지 확인해 주세요`.

Overall score-band and all other `기본 정보` fields are omitted from the model
payload. Risk-management and separate-record data are also omitted from both
the prompt payload and `한주 총평`, regardless of whether a record exists.
The deterministic `위험 관리` detail section remains unchanged. Device
reception likewise describes observation reliability, not subscriber safety
or health.

If any material change or device check exists, the
paragraph must not close with a contradictory generic reassurance such as
`평소처럼 지켜봐 주세요`. Use a relevant approved action once. The ordinary
check-in close is reserved for reports with no attention signal or separate
approved action.

The generated body must be one paragraph with no title, section label,
Markdown, bullets, or explanatory wrapper. It must not contain:

- any digit, score, date, count, ratio, temperature value, or humidity value;
- `움직임`, `리모컨`, or `위험` in any form;
- `GOOD`, `CAUTION`, or `RISK`;
- stiff administrative endings such as `습니다`, `입니다`, `합니다`, or
  `됩니다`;
- sleep or dispatch wording; or
- unsupported medical, safety, cause, or emergency interpretation;
- alarming or rushed words such as `위급`, `긴급`, `즉시`, `서둘러`, `급히`,
  `심각`, `비상`, `경고`, `불안`, `우려`, or `염려`; or
- an exclamation mark.

## Validation and rendering

Validate the complete model paragraph before rendering. Require Korean prose,
one paragraph, body-only formatting, no forbidden digits or words, warm
`해요체`, bounded length, and coverage of every material CAUTION/RISK report
area. Reject all risk-management references, persona-misaligned wording,
actions before the final sentence, and facts introduced after an action. Also
reject a repeated opening topic particle, repeated sentences,
repeated check-in intent, unsupported safety reassurance, and a stable close
that contradicts an attention signal. Also reject the forbidden categorical
word, rushed or alarming wording, and exclamation marks. Allow one bounded
correction request containing only safe validation feedback.

For complete reception absence, require those two sentences and reject any
generic lifestyle assessment or unrelated sensor interpretation. Require a
known usable subscriber name and reject generic substitute honorifics.

`WeeklyNarrative` remains the external compatibility contract. After validation,
split the first sentence into `headline` and the remainder into
`analysis_text`; keep `observations` and `suggestions` empty. The Markdown
renderer joins the two fields with one space so `한주 총평` appears as the
model-authored single paragraph without rewriting it. Deterministic guardian
action cards remain separate.

If model generation or correction fails, use the disclosed deterministic
fallback required by the weekly-reporter reliability policy. Build it from the
same report-facing section descriptions, combine living-activity and
living-pattern trends, strip repeated section-local actions, append at most one
grounded closing action, remove digits and forbidden terms, validate it with
the same paragraph validator, and mark the report as `template_fallback`.

## Reference example

The maintained Markdown fixture is
[`workflows/weekly_report/examples/human-good-report.md`](../../../../workflows/weekly_report/examples/human-good-report.md).
Its numbers come only from Python; its `한주 총평` demonstrates the one-paragraph
LLM composition boundary.
