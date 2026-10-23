"""Static parameterized SQL owned by the weekly-report source service."""

CANDIDATE_WARDS_SQL = """
SELECT w.id AS ward_id, w.full_name
FROM ansimk.resources_ward AS w
WHERE w.id > $1 AND w.has_device IS NOT FALSE
ORDER BY w.id
LIMIT $2
"""

EXPLICIT_WARDS_SQL = """
SELECT id AS ward_id, full_name, has_device
FROM ansimk.resources_ward
WHERE id = ANY($1::bigint[])
ORDER BY id
"""

DAILY_ROWS_SQL = """
SELECT ward_id, device_id, date, temperature, humidity, light,
       light_on_time_minutes, movement_count, remote_control_count,
       wake_up_time, sleep_time, night_awake_count,
       temperature_count, humidity_count, light_count,
       min_temperature, max_temperature, min_humidity, max_humidity,
       min_light, max_light
FROM ansimk.analysis_devicedailysummary
WHERE ward_id = ANY($1::bigint[]) AND date >= $2 AND date < $3
ORDER BY ward_id, date, device_id
"""

RISK_AGGREGATES_SQL = """
WITH periods(period_index, start_at, end_at) AS (
  VALUES (0, $2::timestamptz, $3::timestamptz),
         (1, $3::timestamptz, $4::timestamptz)
), selected(ward_id) AS (SELECT unnest($1::bigint[])),
period_events AS (
  SELECT p.period_index, e.ward_id, e.id, e.evaluated_at,
         e.risk_level, e.risk_score, TRUE AS in_period
  FROM periods p
  JOIN ansimk.analysis_wardevaluation e
    ON e.evaluated_at >= p.start_at AND e.evaluated_at < p.end_at
  JOIN selected s ON s.ward_id = e.ward_id
), seeds AS (
  SELECT p.period_index, s.ward_id, e.id, e.evaluated_at,
         e.risk_level, e.risk_score, FALSE AS in_period
  FROM periods p CROSS JOIN selected s
  JOIN LATERAL (
    SELECT id, evaluated_at, risk_level, risk_score
    FROM ansimk.analysis_wardevaluation
    WHERE ward_id = s.ward_id AND evaluated_at < p.start_at
    ORDER BY evaluated_at DESC, id DESC LIMIT 1
  ) e ON TRUE
), sequenced AS (
  SELECT *, lag(risk_level) OVER (
    PARTITION BY period_index, ward_id ORDER BY evaluated_at, id
  ) AS previous_level
  FROM (SELECT * FROM seeds UNION ALL SELECT * FROM period_events) q
)
SELECT period_index, ward_id,
       count(*) FILTER (WHERE in_period AND risk_level = 'DANGER') AS risk_detected_count,
       count(*) FILTER (
         WHERE in_period AND risk_level = 'STABLE' AND previous_level = 'DANGER'
       ) AS risk_resolved_count,
       avg(risk_score) FILTER (WHERE in_period) AS risk_score_avg,
       count(DISTINCT (evaluated_at AT TIME ZONE $5)::date) FILTER (
         WHERE in_period AND risk_level = 'DANGER'
       ) AS danger_days
FROM sequenced
GROUP BY period_index, ward_id
ORDER BY ward_id, period_index
"""

DISPATCH_AGGREGATES_SQL = """
WITH periods(period_index, start_at, end_at) AS (
  VALUES (0, $2::timestamptz, $3::timestamptz),
         (1, $3::timestamptz, $4::timestamptz)
), selected(ward_id) AS (SELECT unnest($1::bigint[]))
SELECT p.period_index, s.ward_id,
       count(r.id) AS dispatch_request_count,
       count(r.id) FILTER (WHERE NOT r.is_resolved) AS unresolved_dispatch_count
FROM periods p CROSS JOIN selected s
LEFT JOIN ansimk.dispatch_dispatchrequest r
  ON r.ward_id = s.ward_id
 AND r.created_at >= p.start_at AND r.created_at < p.end_at
GROUP BY p.period_index, s.ward_id
ORDER BY s.ward_id, p.period_index
"""
