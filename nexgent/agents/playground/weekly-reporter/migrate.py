"""Operator-only snapshot copy of weekly reports; preview unless --write."""

import argparse
import asyncio
import json
import os
from datetime import date
from pathlib import Path

import asyncpg
from dotenv import dotenv_values, load_dotenv

TABLE = "ansimk.resources_ward_weekly_report"
COLUMNS = (
    "ward_id, week_start_date, week_end_date, weekly_score, weekly_status, "
    "report_data, created_at, updated_at"
)
UPSERT = f"""
INSERT INTO {TABLE} ({COLUMNS})
VALUES ($1, $2, $3, $4, $5, $6::jsonb, COALESCE($7, NOW()), NOW())
ON CONFLICT (ward_id, week_start_date) DO UPDATE SET
    week_end_date = EXCLUDED.week_end_date,
    weekly_score = EXCLUDED.weekly_score,
    weekly_status = EXCLUDED.weekly_status,
    report_data = EXCLUDED.report_data,
    updated_at = NOW()
"""


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing {name}")
    return value


def source_database_dsn():
    """Read only the source DSN from the agent env; never mix target credentials."""
    override = os.environ.get("SOURCE_DATABASE_DSN", "").strip()
    if override:
        return override
    agent_env = dotenv_values(Path(__file__).resolve().parents[2] / ".env")
    for key in ("WEEKLY_REPORT_STORAGE_DATABASE_DSN", "ANSIMK_DATABASE_DSN"):
        value = os.environ.get(key) or agent_env.get(key)
        if value and value.strip():
            return value.strip()
    raise ValueError("Missing source database DSN in agent .env or SOURCE_DATABASE_DSN")


async def migrate(source, target, *, write=False, week_start=None):
    counts = {"source": 0, "insert": 0, "update": 0, "unchanged": 0, "skipped": 0}
    # A stable source snapshot; one target transaction rolls back on any failure.
    async with (
        source.transaction(isolation="repeatable_read", readonly=True),
        target.transaction(isolation="repeatable_read", readonly=not write),
    ):
        if write:
            # Serialize target writes while planning and verifying this copy.
            await target.execute(f"LOCK TABLE {TABLE} IN SHARE ROW EXCLUSIVE MODE")
        query = f"SELECT {COLUMNS} FROM {TABLE}"
        args = []
        if week_start is not None:
            query += " WHERE week_start_date = $1"
            args.append(week_start)
        query += " ORDER BY ward_id, week_start_date"
        async for row in source.cursor(query, *args, prefetch=500):
            counts["source"] += 1
            if not await target.fetchval(
                "SELECT EXISTS(SELECT 1 FROM ansimk.resources_ward WHERE id=$1)",
                row["ward_id"],
            ):
                counts["skipped"] += 1
                print(
                    f"Skipping report: target ward missing, ward_id={row['ward_id']}, "
                    f"week_start_date={row['week_start_date']}; "
                    "report will not be migrated",
                    flush=True,
                )
                continue
            existing = await target.fetchrow(
                "SELECT 1 "
                f"FROM {TABLE} WHERE ward_id=$1 AND week_start_date=$2",
                row["ward_id"],
                row["week_start_date"],
            )
            kind = "insert" if existing is None else "update"
            counts[kind] += 1
            if write:
                result = await target.execute(UPSERT, *tuple(row)[:7])
                if result != "INSERT 0 1":
                    raise ValueError("Unexpected upsert result; transaction aborted")
        return counts


async def run(args):
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    source_dsn = source_database_dsn()
    target_user = required("TARGET_DB_USER")
    target_password = required("TARGET_DB_PASSWORD")
    settings = {"statement_timeout": "60000", "lock_timeout": "5000"}
    print("Connecting to source database...", flush=True)
    source = await asyncpg.connect(source_dsn, timeout=15, server_settings=settings)
    try:
        print("Source connected. Connecting to production through SSH...", flush=True)
        target = await asyncpg.connect(
            host=os.environ.get("TARGET_DB_HOST", "127.0.0.1"),
            port=int(os.environ.get("TARGET_DB_PORT", "15432")),
            database=os.environ.get("TARGET_DB_NAME", "ansimk"),
            user=target_user,
            password=target_password,
            ssl=os.environ.get("TARGET_DB_SSL", "require"),
            timeout=15,
            server_settings=settings,
        )
        try:
            print("Production connected. Checking selected reports...", flush=True)
            identity_sql = "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
            if await source.fetchrow(identity_sql) == await target.fetchrow(
                identity_sql
            ):
                raise ValueError(
                    "Source and target appear identical; migration aborted"
                )
            counts = await migrate(
                source,
                target,
                write=args.write,
                week_start=args.week_start,
            )
            print(
                json.dumps({"mode": "committed" if args.write else "preview", **counts})
            )
        finally:
            await target.close()
    finally:
        await source.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="Commit production upserts"
    )
    parser.add_argument(
        "--week-start", type=date.fromisoformat, help="Limit to YYYY-MM-DD"
    )
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except ValueError as exc:
        # Configuration and operator errors contain no DSNs or report content.
        print(str(exc))
        return 1
    except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
        error_code = getattr(exc, "sqlstate", None) or getattr(exc, "errno", None)
        print(
            f"Database operation failed: {type(exc).__name__} (code={error_code}). "
            "No success confirmed. The last progress line identifies the failing stage."
        )
        if isinstance(exc, ConnectionError) and "rejected SSL upgrade" in str(exc):
            print("The database server rejected required TLS (SSL) negotiation.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
