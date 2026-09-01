# Korean weekly narrative style

Use the product-owner-promoted spreadsheet wording tab for deterministic
section classifications, section copy, and guardian-action rules. Database
facts and all calculations still enter through validated Python contracts.

## Summary ownership

`한주 총평` is authored as a complete paragraph by the LLM. Python must not
select an exact activity-combination sentence, calculate a summary mode, or
assemble the normal LLM summary from formula-owned prose.

The LLM receives only report-facing, Python-verified weekly data:

- subscriber display name;
- overall score-band status and approved Korean explanation, without the
  numeric score;
- `생활 활동`, `생활 패턴`, `실내 환경`, and `기기 상태` status,
  description, and short summary;
- the qualitative risk-management result; and
- already-approved guardian-action titles.

Do not send raw rows, totals, ratios, thresholds, dates, sensor measurements,
management notes, sleep data, dispatch data, `summary_outline`,
`required_topics`, or Python-composed summary sentences to the LLM.

## Prompt and output

Prompt version `weekly-korean-free-summary-v21` uses the product-owner-supplied
system prompt verbatim apart from replacing `{{WEEKLY_REPORT_DATA}}` with the
validated JSON payload. The model returns only the completed Korean summary
body, not JSON and not separate headline, observation, or suggestion fields.

The paragraph should:

- sound like a person who watched the week explaining it warmly to a guardian;
- connect overall state, notable changes, indoor environment, device state,
  and a grounded close as one short story;
- use respectful, natural `해요체`;
- avoid diagnostic, causal, urgent, categorical, or anxiety-amplifying claims;
- treat missing or incomparable data as a limitation, never an abnormal
  condition; and
- avoid inventing an action when no approved action exists, beyond asking the
  guardian to continue watching as usual.

The generated body must be one paragraph with no title, section label,
Markdown, bullets, or explanatory wrapper. It must not contain:

- any digit, score, date, count, ratio, temperature value, or humidity value;
- `움직임` or `리모컨` in any form;
- `GOOD`, `CAUTION`, or `RISK`;
- stiff administrative endings such as `습니다`, `입니다`, `합니다`, or
  `됩니다`;
- sleep or dispatch wording; or
- unsupported medical, safety, cause, or emergency interpretation.

## Validation and rendering

Validate the complete model paragraph before rendering. Require Korean prose,
one paragraph, body-only formatting, no forbidden digits or words, warm
`해요체`, bounded length, and coverage of every material CAUTION/RISK report
area. Allow one bounded correction request containing only safe validation
feedback.

`WeeklyNarrative` remains the external compatibility contract. After validation,
split the first sentence into `headline` and the remainder into
`analysis_text`; keep `observations` and `suggestions` empty. The Markdown
renderer joins the two fields with one space so `한주 총평` appears as the
model-authored single paragraph without rewriting it. Deterministic guardian
action cards remain separate.

If model generation or correction fails, use the disclosed deterministic
fallback required by the weekly-reporter reliability policy. Build it from the
same report-facing section descriptions, remove digits and forbidden terms,
validate it with the same paragraph validator, and mark the report as
`template_fallback`.

## Reference example

The maintained Markdown fixture is
[`workflows/weekly_report/examples/human-good-report.md`](../../../../workflows/weekly_report/examples/human-good-report.md).
Its numbers come only from Python; its `한주 총평` demonstrates the one-paragraph
LLM composition boundary.
