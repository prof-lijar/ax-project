"""Run a previous-day risk reconciliation; preview unless --apply is given."""

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import asyncpg
from dotenv import dotenv_values, load_dotenv

from workflows.daily_risk_counts.workflow import TIMEZONE, previous_day, reconcile_day

ROOT = Path(__file__).resolve().parents[2]


def database_dsn() -> str:
    # Match the existing manual migration's local connection precedence.
    load_dotenv(ROOT / "playground/.env", override=False)
    settings = dotenv_values(ROOT / ".env")
    for key in (
        "SOURCE_DATABASE_DSN",
        "WEEKLY_REPORT_STORAGE_DATABASE_DSN",
        "ANSIMK_DATABASE_DSN",
    ):
        value = os.environ.get(key)
        if key != "SOURCE_DATABASE_DSN" and not value:
            value = settings.get(key)
        if value and value.strip():
            return value.strip()
    raise ValueError("Missing local source/storage database DSN")


def event(name: str, **fields) -> None:
    print(
        json.dumps(
            {"event": name, "timestamp": datetime.now(TIMEZONE).isoformat(), **fields}
        ),
        flush=True,
    )


async def run(day: date, *, apply: bool) -> None:
    event("daily_risk_started", date=day.isoformat(), apply=apply)
    connection = await asyncpg.connect(
        database_dsn(),
        timeout=15,
        command_timeout=1830,
        server_settings={"application_name": "daily_risk_counts"},
    )
    try:
        result = await reconcile_day(connection, day, apply=apply)
        event("daily_risk_completed", **result)
    finally:
        await connection.close(timeout=10)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        help="Completed date YYYY-MM-DD; default yesterday in Seoul",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Commit changes (cron uses this flag)"
    )
    args = parser.parse_args(argv)
    day = args.date or previous_day()
    if day > previous_day():
        parser.error("--date must be before today in Asia/Seoul")
    try:
        asyncio.run(run(day, apply=args.apply))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 -- sanitize failures at the CLI boundary
        # Never include driver messages, DSNs, credentials or ward data.
        event(
            "daily_risk_failed",
            date=day.isoformat(),
            error_type=type(exc).__name__,
            sqlstate=getattr(exc, "sqlstate", None),
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
