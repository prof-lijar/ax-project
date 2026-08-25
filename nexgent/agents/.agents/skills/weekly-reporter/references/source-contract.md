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
- Arithmetic-average activity and night-awake values over non-null rows.
- Average clock times linearly to preserve existing service behavior.
- Count `DANGER` evaluations; count distinct local danger dates separately.
- Count `DANGER` to `STABLE` transitions, seeded by the final pre-period event.
- Average non-null risk scores, then apply the approved presentation policy below.
- Count dispatches by `created_at`; unresolved means current `is_resolved=false`.
- Recompute both weeks from raw records.

## Approved environment interpretation

The product owner approved a versioned presentation rule on 2026-08-20. Use
the reporting week's starting month to select the indoor temperature range:

- January through March: 18–20℃;
- April and May: 20–22℃;
- June through September: 26–28℃;
- October: 20–22℃;
- November and December: 18–20℃.

The product owner revised this presentation rule on 2026-08-24. Compare only
the current week's stored maximum temperature and maximum humidity with the
applicable ranges. Classify each available maximum and use the more severe
result as the overall environment status:

- `GOOD`: temperature is inside that month's recommended range and humidity is
  inside 40–60%;
- `CAUTION`: temperature is outside the recommended range but remains within
  15–30℃, or humidity is outside 40–60% but remains within 30–70%;
- `RISK`: temperature is below 15℃ or above 30℃, or humidity is below 30% or
  above 70%.

The endpoints 15℃, 30℃, 30%, and 70% belong to `CAUTION`. Render a precise,
calm explanation tied to the maximum that caused the status. The current
snapshot does not contain daily range-departure counts, so do not claim that a
condition repeated or continued for a number of days. These are report guidance
labels, not diagnoses or evidence of a health condition. The numeric rules
remain in deterministic Python and the model sees only their qualitative
result.

## Approved risk-score interpretation

The product owner approved a versioned weekly-average presentation rule on
2026-08-24. Average the current week's non-null `risk_score` values, round the
result to the nearest whole point using half-up rounding, and render these
bands:

- 76–100: `양호`;
- 26–75: `주의`;
- 0–25: `위험`.

Render the rounded score and its calm Korean band description from
deterministic Python without the full range legend. When no score exists or a
source value is outside 0–100, disclose that the score data is unavailable. Do
not send the numeric score or its band to the model, and do not treat the band
as a diagnosis or certainty that an incident occurred.

## API and security

Use `POST /internal/v1/weekly-report/source` with `WeeklyReportRequest` and
`WeeklyReportSourceResponse`. Keep the service on the private application
network and require parameterized application-owned SQL, pooled read-only
transactions, bounded timeouts, safe errors, and readiness checks. Never expose
a generic query endpoint.
