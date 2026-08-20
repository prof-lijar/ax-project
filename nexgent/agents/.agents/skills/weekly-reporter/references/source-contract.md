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
  evaluations, and dispatches. Sort by ward ID and cap each page at twenty-five.
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
- Average non-null risk scores without assigning good/bad meaning.
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

The approved humidity range is 40–60% in every month. Classify a weekly
minimum below the lower bound as a cold or dry interval and a weekly maximum
above the upper bound as a hot or humid interval. When both occur, disclose
both. These are report guidance labels, not diagnoses or evidence of a health
condition. The numeric rules remain in deterministic Python and the model sees
only their qualitative result.

## API and security

Use `POST /internal/v1/weekly-report/source` with `WeeklyReportRequest` and
`WeeklyReportSourceResponse`. Keep the service on the private application
network and require parameterized application-owned SQL, pooled read-only
transactions, bounded timeouts, safe errors, and readiness checks. Never expose
a generic query endpoint.
