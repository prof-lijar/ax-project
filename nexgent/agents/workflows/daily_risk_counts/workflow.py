"""Reconcile one completed Seoul date into the existing monthly risk table."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Asia/Seoul")
TARGET_TABLE = "archive.resources_ward_monthly_risk_count"


def previous_day(now: datetime | None = None) -> date:
    now = now or datetime.now(TIMEZONE)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("An aware timestamp is required")
    return now.astimezone(TIMEZONE).date() - timedelta(days=1)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(day, time.min, TIMEZONE),
        datetime.combine(day + timedelta(days=1), time.min, TIMEZONE),
    )


# Both DANGER and STABLE use the same half-open local-day window. Only this
# day's membership is replaced; historical day membership is retained.
EXPECTED_SQL = """
WITH danger AS (
    SELECT ward_id, MIN(evaluated_at) AS first_danger
    FROM archive.analysis_wardevaluation
    WHERE evaluated_at >= $1::timestamptz
      AND evaluated_at < $2::timestamptz AND risk_level = 'DANGER'
    GROUP BY ward_id
), daily AS (
    SELECT d.ward_id, EXISTS (
        SELECT 1 FROM archive.analysis_wardevaluation s
        WHERE s.ward_id = d.ward_id AND s.risk_level = 'STABLE'
          AND s.evaluated_at > d.first_danger
          AND s.evaluated_at < $2::timestamptz
    ) AS recovered FROM danger d
), merged AS (
    SELECT w.id AS ward_id, $3::varchar(7) AS month,
        ARRAY(
            SELECT DISTINCT n FROM unnest(
                array_remove(COALESCE(t.risk_days, ARRAY[]::integer[]), $4::int)
                || CASE WHEN d.ward_id IS NOT NULL THEN ARRAY[$4::int]
                        ELSE ARRAY[]::integer[] END
            ) n ORDER BY n
        ) AS risk_days,
        ARRAY(
            SELECT DISTINCT n FROM unnest(
                array_remove(COALESCE(t.danger_stable_days, ARRAY[]::integer[]), $4::int)
                || CASE WHEN d.recovered THEN ARRAY[$4::int]
                        ELSE ARRAY[]::integer[] END
            ) n ORDER BY n
        ) AS danger_stable_days
    FROM archive.resources_ward w
    LEFT JOIN daily d ON d.ward_id = w.id
    LEFT JOIN archive.resources_ward_monthly_risk_count t
        ON t.ward_id = w.id AND t.month = $3::varchar(7)
), expected AS (
    SELECT *, cardinality(risk_days) AS total_risk_count,
              cardinality(danger_stable_days) AS total_danger_stable_count
    FROM merged
)
"""

DIFFERENT_SQL = """
ROW(t.total_risk_count, t.risk_days, t.total_danger_stable_count, t.danger_stable_days)
IS DISTINCT FROM
ROW(e.total_risk_count, e.risk_days, e.total_danger_stable_count, e.danger_stable_days)
"""

PREVIEW_SQL = (
    EXPECTED_SQL
    + """
SELECT COUNT(*)::bigint AS wards,
       COUNT(*) FILTER (WHERE t.id IS NULL)::bigint AS inserts,
       COUNT(*) FILTER (WHERE t.id IS NOT NULL AND (
"""
    + DIFFERENT_SQL
    + """))::bigint AS updates
FROM expected e LEFT JOIN archive.resources_ward_monthly_risk_count t
    ON t.ward_id = e.ward_id AND t.month = e.month
"""
)

UPSERT_SQL = (
    EXPECTED_SQL
    + """
, written AS (
    INSERT INTO archive.resources_ward_monthly_risk_count AS t (
        ward_id, month, total_risk_count, risk_days,
        total_danger_stable_count, danger_stable_days
    )
    SELECT ward_id, month, total_risk_count, risk_days,
           total_danger_stable_count, danger_stable_days FROM expected WHERE TRUE
    ON CONFLICT (ward_id, month) DO UPDATE SET
        total_risk_count = EXCLUDED.total_risk_count,
        risk_days = EXCLUDED.risk_days,
        total_danger_stable_count = EXCLUDED.total_danger_stable_count,
        danger_stable_days = EXCLUDED.danger_stable_days,
        updated_at = NOW()
    WHERE ROW(t.total_risk_count, t.risk_days,
              t.total_danger_stable_count, t.danger_stable_days)
          IS DISTINCT FROM
          ROW(EXCLUDED.total_risk_count, EXCLUDED.risk_days,
              EXCLUDED.total_danger_stable_count, EXCLUDED.danger_stable_days)
    RETURNING 1
)
SELECT COUNT(*)::bigint FROM written
"""
)


async def reconcile_day(connection, day: date, *, apply: bool = False) -> dict:
    """One atomic date; the committed table is the durable recovery checkpoint."""
    if day > previous_day():
        raise ValueError("Only completed local dates can be processed")
    start, end = day_bounds(day)
    month = day.strftime("%Y.%m")
    params = (start, end, month, day.day)
    async with connection.transaction(isolation="repeatable_read", readonly=not apply):
        await connection.execute("SET LOCAL lock_timeout = '10s'")
        await connection.execute("SET LOCAL statement_timeout = '30min'")
        if apply:
            # Same table lock as the manual monthly migration. Acquire before
            # the first source snapshot so concurrent runs cannot lose updates.
            await connection.execute(
                f"LOCK TABLE {TARGET_TABLE} IN SHARE ROW EXCLUSIVE MODE"
            )
        summary = dict(await connection.fetchrow(PREVIEW_SQL, *params))
        summary["unchanged"] = (
            summary["wards"] - summary["inserts"] - summary["updates"]
        )
        if apply:
            summary["written"] = await connection.fetchval(UPSERT_SQL, *params)
            if summary["written"] != summary["inserts"] + summary["updates"]:
                raise RuntimeError("Write count mismatch; transaction rolled back")
    return {
        "date": day.isoformat(),
        "month": month,
        "timezone": TIMEZONE.key,
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "mode": "committed" if apply else "preview",
        **summary,
    }
