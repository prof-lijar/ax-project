"""Recalculate monthly DANGER and same-day recovery counts. Preview unless --apply is supplied."""

import argparse
import asyncio
import json
import os
import re
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"


def log(message, *, file=None):
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"[{timestamp}] {message}", file=file, flush=True)


@asynccontextmanager
async def progress(message):
    """Keep long database operations visibly active without extra DB queries."""
    started = monotonic()
    log(message)

    async def heartbeat():
        while True:
            await asyncio.sleep(15)
            log(f"{message} — still running; elapsed={monotonic() - started:.1f}s")

    task = asyncio.create_task(heartbeat())
    try:
        yield
    except Exception as exc:
        log(f"{message} — failed ({type(exc).__name__})", file=sys.stderr)
        raise
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def source_database_dsn():
    """Use the same archive connection settings as weekly-reporter/migrate.py."""
    override = os.environ.get("SOURCE_DATABASE_DSN", "").strip()
    if override:
        return override
    agent_env = dotenv_values(ROOT / ".env")
    for key in ("WEEKLY_REPORT_STORAGE_DATABASE_DSN", "ANSIMK_DATABASE_DSN"):
        value = os.environ.get(key) or agent_env.get(key)
        if value and value.strip():
            return value.strip()
    raise ValueError(
        "Missing source database DSN in agents/.env or SOURCE_DATABASE_DSN"
    )


# $1/$2: inclusive/exclusive month bounds; $3: timezone; $4: YYYY.MM.
# Filter the original timestamp column so PostgreSQL can use its indexes.
COUNTS_SQL = """
WITH danger_days AS (
    SELECT ward_id,
           (evaluated_at AT TIME ZONE $3::text)::date AS risk_date,
           MIN(evaluated_at) AS first_danger
    FROM archive.analysis_wardevaluation
    WHERE risk_level = 'DANGER'
      AND evaluated_at >= $1::timestamptz
      AND evaluated_at < $2::timestamptz
    GROUP BY ward_id, (evaluated_at AT TIME ZONE $3::text)::date
),
daily AS (
    -- Probe only this ward's remaining local day, using its timestamp index.
    -- Intermediate evaluations are allowed; equal timestamps do not qualify.
    SELECT d.ward_id, d.risk_date,
           EXISTS (
               SELECT 1 FROM archive.analysis_wardevaluation AS stable
               WHERE stable.ward_id = d.ward_id AND stable.risk_level = 'STABLE'
                 AND stable.evaluated_at > d.first_danger
                 AND stable.evaluated_at <
                     ((d.risk_date + 1)::timestamp AT TIME ZONE $3::text)
           ) AS became_stable
    FROM danger_days d
),
totals AS (
    SELECT ward_id,
           COUNT(*)::int AS total_risk_count,
           ARRAY_AGG(EXTRACT(DAY FROM risk_date)::int ORDER BY risk_date) AS risk_days,
           COUNT(*) FILTER (WHERE became_stable)::int
               AS total_danger_stable_count,
           ARRAY_AGG(EXTRACT(DAY FROM risk_date)::int ORDER BY risk_date)
               FILTER (WHERE became_stable) AS danger_stable_days
    FROM daily
    GROUP BY ward_id
),
expected AS (
    SELECT w.id AS ward_id, $4::varchar(7) AS month,
           COALESCE(t.total_risk_count, 0) AS total_risk_count,
           COALESCE(t.risk_days, ARRAY[]::integer[]) AS risk_days,
           COALESCE(t.total_danger_stable_count, 0) AS total_danger_stable_count,
           COALESCE(t.danger_stable_days, ARRAY[]::integer[]) AS danger_stable_days
    FROM archive.resources_ward w
    LEFT JOIN totals t ON t.ward_id = w.id
)
"""

PREVIEW_SQL = (
    COUNTS_SQL
    + """
SELECT COUNT(*)::bigint AS wards,
       COUNT(*) FILTER (WHERE t.id IS NULL)::bigint AS inserts,
       COUNT(*) FILTER (
           WHERE t.id IS NOT NULL AND
                 ROW(t.total_risk_count, t.risk_days,
                     t.total_danger_stable_count, t.danger_stable_days)
                 IS DISTINCT FROM
                 ROW(e.total_risk_count, e.risk_days,
                     e.total_danger_stable_count, e.danger_stable_days)
       )::bigint AS updates,
       COALESCE(SUM(e.total_risk_count), 0)::bigint AS danger_days,
       COALESCE(SUM(e.total_danger_stable_count), 0)::bigint AS danger_stable_days
FROM expected e
LEFT JOIN archive.resources_ward_monthly_risk_count t
       ON t.ward_id = e.ward_id AND t.month = e.month
"""
)

UPSERT_SQL = (
    COUNTS_SQL
    + """
, written AS (
    INSERT INTO archive.resources_ward_monthly_risk_count AS target (
        ward_id, month, total_risk_count, risk_days,
        total_danger_stable_count, danger_stable_days
    )
    SELECT ward_id, month, total_risk_count, risk_days,
           total_danger_stable_count, danger_stable_days
    FROM expected
    WHERE TRUE
    ON CONFLICT (ward_id, month) DO UPDATE SET
        total_risk_count = EXCLUDED.total_risk_count,
        risk_days = EXCLUDED.risk_days,
        total_danger_stable_count = EXCLUDED.total_danger_stable_count,
        danger_stable_days = EXCLUDED.danger_stable_days,
        updated_at = NOW()
    WHERE ROW(target.total_risk_count, target.risk_days,
              target.total_danger_stable_count, target.danger_stable_days)
          IS DISTINCT FROM
          ROW(EXCLUDED.total_risk_count, EXCLUDED.risk_days,
              EXCLUDED.total_danger_stable_count, EXCLUDED.danger_stable_days)
    RETURNING 1
)
SELECT COUNT(*)::bigint FROM written
"""
)


def parse_month(value):
    if not re.fullmatch(r"[0-9]{4}[-.](0[1-9]|1[0-2])", value):
        raise argparse.ArgumentTypeError("Use YYYY-MM or YYYY.MM.")
    try:
        result = date(int(value[:4]), int(value[5:]), 1)
        next_month(result)  # Ensure the exclusive upper boundary is representable.
        return result
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Month is outside the supported range."
        ) from exc


def next_month(month):
    if month.month == 12:
        return date(month.year + 1, 1, 1)
    return date(month.year, month.month + 1, 1)


def months_between(start, end):
    while start <= end:
        yield start
        start = next_month(start)


def month_bounds(month, timezone):
    following = next_month(month)
    return (
        datetime(month.year, month.month, 1, tzinfo=timezone),
        datetime(following.year, following.month, 1, tzinfo=timezone),
    )


async def resolve_month_range(connection, start, end, timezone):
    """Infer the full source history only when both bounds are omitted."""
    if (start is None) != (end is None):
        raise ValueError("Supply both --start-month and --end-month, or neither.")
    if start is not None:
        if start > end:
            raise ValueError("--start-month must not be after --end-month")
        return start, end
    row = await connection.fetchrow(
        "SELECT MIN(evaluated_at) AS first_evaluation, "
        "MAX(evaluated_at) AS last_evaluation "
        "FROM archive.analysis_wardevaluation",
        timeout=60,
    )
    if row["first_evaluation"] is None:
        return None
    start = row["first_evaluation"].astimezone(timezone).date().replace(day=1)
    end = row["last_evaluation"].astimezone(timezone).date().replace(day=1)
    next_month(end)  # Validate before any monthly writes.
    return start, end


async def migrate(connection, start, end, timezone, apply=False):
    total = (end.year - start.year) * 12 + end.month - start.month + 1
    started = monotonic()
    for index, month in enumerate(months_between(start, end), start=1):
        month_started = monotonic()
        label = f"{month.year:04d}.{month.month:02d}"
        prefix = f"[{index}/{total}] {label}"
        params = (*month_bounds(month, timezone), timezone.key, label)
        # Each month's plan and write see the same source snapshot.
        async with (
            progress(f"{prefix} Processing month"),
            connection.transaction(isolation="repeatable_read", readonly=not apply),
        ):
            await connection.execute("SET LOCAL lock_timeout = '10s'")
            await connection.execute("SET LOCAL statement_timeout = '30min'")
            if apply:
                log(f"{prefix} Waiting for target table lock")
                # Prevent competing writes from invalidating the plan. Ordinary
                # SELECTs are permitted; lock is released at this month's commit.
                await connection.execute(
                    "LOCK TABLE archive.resources_ward_monthly_risk_count "
                    "IN SHARE ROW EXCLUSIVE MODE"
                )
            log(
                f"{prefix} Counting DANGER and same-day recovery days; comparing target rows"
            )
            summary = dict(await connection.fetchrow(PREVIEW_SQL, *params))
            summary["unchanged"] = (
                summary["wards"] - summary["inserts"] - summary["updates"]
            )
            log(
                f"{prefix} Plan: wards={summary['wards']}, "
                f"inserts={summary['inserts']}, updates={summary['updates']}, "
                f"unchanged={summary['unchanged']}, "
                f"danger_days={summary['danger_days']}, "
                f"danger_stable_days={summary['danger_stable_days']}"
            )
            if apply:
                log(f"{prefix} Writing recalculated counts")
                written = await connection.fetchval(UPSERT_SQL, *params)
                if written != summary["inserts"] + summary["updates"]:
                    raise RuntimeError("Unexpected write count; month rolled back.")
                summary["written"] = written
                log(f"{prefix} Committing transaction")
        # Only report success after the transaction exits successfully.
        print(
            json.dumps(
                {
                    "timestamp": datetime.now()
                    .astimezone()
                    .isoformat(timespec="seconds"),
                    "month": label,
                    "mode": "committed" if apply else "preview",
                    "completed_months": index,
                    "total_months": total,
                    "progress_percent": round(index / total * 100, 1),
                    "elapsed_seconds": round(monotonic() - month_started, 1),
                    **summary,
                }
            ),
            flush=True,
        )
    log(
        f"{'Migration' if apply else 'Preview'} complete: {total}/{total} months; "
        f"elapsed={monotonic() - started:.1f}s"
    )


async def run(args, dsn, timezone):
    try:
        import asyncpg
    except ImportError as exc:
        raise RuntimeError(
            "Run with bash playground/migrate/run.sh using the workspace .venv."
        ) from exc

    async with progress("Connecting to archive database"):
        connection = await asyncpg.connect(
            dsn,
            timeout=15,
            command_timeout=1830,
            server_settings={"application_name": "migrate_weekly_risk_counts"},
        )
    try:
        log("Database connected")
        async with progress("Resolving evaluation month range"):
            month_range = await resolve_month_range(
                connection, args.start_month, args.end_month, timezone
            )
        if month_range is None:
            log("No evaluations found; nothing to migrate.")
            return
        start, end = month_range
        log(
            f"Month range: {start:%Y-%m} through {end:%Y-%m} (inclusive)",
        )
        await migrate(connection, start, end, timezone, args.apply)
    finally:
        await connection.close(timeout=10)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-month",
        type=parse_month,
        help="First month; omit both month options to use the full evaluation history.",
    )
    parser.add_argument("--end-month", type=parse_month, help="Inclusive final month.")
    parser.add_argument("--timezone", default="Asia/Seoul")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes; otherwise run a read-only preview.",
    )
    args = parser.parse_args(argv)
    if (args.start_month is None) != (args.end_month is None):
        parser.error("Supply both --start-month and --end-month, or neither.")
    if args.start_month is not None and args.start_month > args.end_month:
        parser.error("--start-month must not be after --end-month")
    return parser, args


def main():
    parser, args = parse_args()
    try:
        timezone = ZoneInfo(args.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        parser.error("Unknown timezone.")
    load_dotenv(ENV_FILE, override=False)
    try:
        dsn = source_database_dsn()
    except ValueError as exc:
        parser.error(str(exc))
    log(
        f"Mode: {'APPLY' if args.apply else 'PREVIEW'}; timezone: {timezone.key}; "
        "count: at most 1 per ward per DANGER day; "
        "recovery: STABLE strictly later than DANGER on the same local date",
    )
    try:
        asyncio.run(run(args, dsn, timezone))
    except KeyboardInterrupt:
        log("Interrupted; rerun the same range to resume.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 -- sanitize errors at the CLI boundary
        # Driver messages may contain connection credentials or row contents.
        log(
            f"Migration failed ({type(exc).__name__}, "
            f"SQLSTATE={getattr(exc, 'sqlstate', None) or 'n/a'}). "
            "The current month was not confirmed; earlier months may be committed. "
            "Rerun the same range after resolving the error. "
            "Use the workspace .venv and check the shared database settings.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
