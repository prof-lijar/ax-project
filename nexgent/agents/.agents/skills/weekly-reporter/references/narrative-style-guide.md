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
- When `실내 환경` is required, mention the supplied temperature or humidity
  status in `analysis_text` without repeating numeric thresholds.

## Prohibited interpretations

- Do not diagnose or describe medical symptoms.
- Do not infer causes from sensor changes.
- Do not state that an accident, disease, danger, or emergency certainly
  occurred.
- Do not amplify anxiety or use categorical wording such as “위험합니다.”
- Do not assume the reason for a dispatch.
- Do not treat missing device data as evidence of a health problem.
- Do not invent score thresholds or classify raw environment readings beyond
  the separately approved versioned monthly temperature and humidity policy.

Prioritize incomplete data disclosure, unresolved dispatch state, risk-event
changes, activity, sleep, environment, then stable observations. The priority
chooses what to mention; it does not assign a medical or safety conclusion.
