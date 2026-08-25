# Korean weekly narrative style

Use the referenced spreadsheet wording tab as a tone reference, not a source of
numeric rules.

## Desired voice

- Write warm, calm, natural Korean for a guardian or care manager.
- Start with the overall weekly flow and group stable observations naturally.
- Describe observed changes gently and distinguish data limitations from the
  person’s condition.
- Use recommendation language such as “확인해 보셔도 좋아요.”
- Keep suggestions relevant and limit them to three.

## Output

- Return JSON keys `headline`, `analysis_text`, `observations`, `suggestions`.
- Write four to six analysis sentences totaling 220–420 characters.
- Keep model-authored prose digit-free. Show verified numbers only in the
  deterministic renderer.
- Discuss only allowlisted qualitative topics supplied by Python.
- Keep suggestions grounded in the supplied observations. The deterministic
  renderer may repeat the highest-priority suggestion in `한주 총평` so the
  assessment ends with one warm, relevant next step.
- When `실내 환경` is required, mention the supplied maximum-temperature or
  maximum-humidity status in `analysis_text` without repeating numeric thresholds.

## Prohibited interpretations

- Do not diagnose or describe medical symptoms.
- Do not infer causes from sensor changes.
- Do not state that an accident, disease, danger, or emergency certainly
  occurred.
- Do not amplify anxiety or use categorical wording such as “위험합니다.”
- Do not assume the reason for a dispatch.
- Do not treat missing device data as evidence of a health problem.
- Do not invent score thresholds. The separately approved weekly-average score
  bands are rendered by deterministic Python and are not model-authored prose.
- Do not classify raw environment readings beyond the separately approved
  versioned maximum-temperature and maximum-humidity policy.
- Do not claim repeated conditions or a count of affected days unless Python
  supplies a validated daily count.

Prioritize incomplete data disclosure, unresolved dispatch state, risk-event
changes, activity, sleep, environment, then stable observations. The priority
chooses what to mention; it does not assign a medical or safety conclusion.
