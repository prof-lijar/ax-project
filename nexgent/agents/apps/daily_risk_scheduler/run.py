"""Run a previous-day risk reconciliation; preview unless --apply is given."""

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import asyncpg
from dotenv import dotenv_values

from apps.daily_risk_scheduler.notification import notify_status
from workflows.daily_risk_counts.workflow import TIMEZONE, previous_day, reconcile_day

ROOT = Path(__file__).resolve().parents[2]


def database_dsn() -> str:
    # Only the unified workspace file and explicit process overrides are used.
    settings = dotenv_values(ROOT / ".env")
    for key in (
        "SOURCE_DATABASE_DSN",
        "WEEKLY_REPORT_STORAGE_DATABASE_DSN",
        "ANSIMK_DATABASE_DSN",
    ):
        value = os.environ.get(key)
        if not value:
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
    started_at = datetime.now(TIMEZONE)
    event("daily_risk_started", date=day.isoformat(), apply=apply)
    stage = "Database configuration"
    try:
        dsn = database_dsn()
        stage = "Database connection"
        connection = await asyncpg.connect(
            dsn,
            timeout=15,
            command_timeout=1830,
            server_settings={"application_name": "daily_risk_counts"},
        )
        try:
            stage = "Database reconciliation or commit confirmation"
            result = await reconcile_day(connection, day, apply=apply)
        finally:
            # Connection cleanup must not turn a committed run into a failure.
            try:
                await connection.close(timeout=10)
            except Exception as exc:  # noqa: BLE001 -- sanitize cleanup failures
                event("daily_risk_cleanup_failed", error_type=type(exc).__name__)
    except Exception as exc:
        event(
            "daily_risk_failed",
            date=day.isoformat(),
            error_type=type(exc).__name__,
            sqlstate=getattr(exc, "sqlstate", None),
        )
        if apply:
            await notify_status(
                day,
                started_at=started_at,
                ended_at=datetime.now(TIMEZONE),
                issue=f"{stage} failed. Check daily_risk_failed logs for details.",
                event=event,
            )
        raise
    event("daily_risk_completed", **result)
    if apply:
        await notify_status(
            day, started_at=started_at, ended_at=datetime.now(TIMEZONE), event=event
        )


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
    except Exception:  # noqa: BLE001 -- already sanitized and logged in run()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
