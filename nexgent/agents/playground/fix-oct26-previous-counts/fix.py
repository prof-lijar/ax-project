"""One-time saved-report correction for October 26–November 1, 2026; preview by default."""

import argparse
import asyncio
import copy
import json
import math
import os
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import asyncpg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from workflows.weekly_report.domain.activity_policy import (
    _classify,
)
from workflows.weekly_report.domain.rendering import (
    _number,
    _percentage,
)

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE.parent.parent / ".env"
TABLES = {
    "local": "archive.resources_ward_weekly_report",
    "prod": "ansimk.resources_ward_weekly_report",
}
WEEK = date(2026, 10, 26)
BASELINE_WEEK = date(2026, 10, 19)
SIGNALS = ("activity_detection", "remote_control_usage")
SELECT = """
SELECT ward_id, week_start_date, week_end_date, weekly_score, weekly_status,
       report_data, created_at, updated_at
FROM {table}
WHERE week_start_date IN ($1, $2)
ORDER BY ward_id, week_start_date
"""
UPDATE = """
UPDATE {table} SET report_data=$3::jsonb, updated_at=NOW()
WHERE ward_id=$1 AND week_start_date=$2 AND report_data=$4::jsonb
"""


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing {name}; configure {ENV_FILE.name}")
    return value


def document(row, week):
    """Require exact calendar dates, including the dates inside the stored JSON."""
    if row["week_start_date"] != week or row["week_end_date"] != week + timedelta(
        days=6
    ):
        raise ValueError("invalid_period")
    data = row["report_data"]
    data = json.loads(data) if isinstance(data, str) else data
    period = data["basic_info"]["period"]
    if (
        period["start_date"] != week.isoformat()
        or period["end_date"] != (week + timedelta(days=6)).isoformat()
    ):
        raise ValueError("invalid_period")
    return data


def count(metrics, key):
    value = metrics[key]  # An absent key is invalid, not an unavailable count.
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("invalid_count")
    return float(value)


def plan_report(current, baseline):
    """Match saved previous counts regardless of classification or narrative."""
    result = {"ward_id": current["ward_id"], "status": "missing_baseline"}
    if baseline is None:
        return result, None
    try:
        if current["ward_id"] != baseline["ward_id"]:
            raise ValueError("ward_mismatch")
        old = document(current, WEEK)
        previous = document(baseline, BASELINE_WEEK)
        patched = copy.deepcopy(old)
        changes = {}
        for signal in SIGNALS:
            section = old["living_activity"][signal]
            metrics = section["metrics"]
            actual = count(metrics, "current_week")
            old_prior = count(metrics, "previous_week")
            new_prior = count(
                previous["living_activity"][signal]["metrics"], "current_week"
            )
            before = _classify(actual, old_prior)
            after = _classify(actual, new_prior)
            changes[signal] = {
                "current": actual,
                "previous_before": old_prior,
                "previous_after": new_prior,
                "percent_before": before.ratio_percent,
                "percent_after": after.ratio_percent,
                "classification_before": [before.status, before.trend],
                "classification_after": [after.status, after.trend],
            }
            patched["living_activity"][signal]["metrics"].update(
                previous_week=new_prior,
                previous_week_display=_number(new_prior, "회"),
                comparison_percent=after.ratio_percent,
                comparison_display=_percentage(after),
            )
        result["changes"] = changes
        result["status"] = "unchanged" if patched == old else "update"
        return result, patched
    except (KeyError, TypeError, ValueError, OverflowError):
        # Never print raw JSON, subscriber names, or parser error context.
        result["status"] = "invalid_report"
        return result, None


def save_artifact(directory, payload):
    """Create a private, non-overwriting snapshot and flush it before any UPDATE."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{stamp}-{uuid4().hex}.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump(payload, file, ensure_ascii=False, default=str, allow_nan=False)
        file.flush()
        os.fsync(file.fileno())
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return path


async def correct(connection, *, target, write, output_dir):
    """Commit eligible rows atomically within one selected database."""
    table = TABLES[target]
    async with connection.transaction(isolation="repeatable_read", readonly=not write):
        # Lock both baseline and destination rows against concurrent regeneration.
        rows = await connection.fetch(
            SELECT.format(table=table) + (" FOR UPDATE" if write else ""),
            BASELINE_WEEK,
            WEEK,
        )
        baselines = {
            r["ward_id"]: r for r in rows if r["week_start_date"] == BASELINE_WEEK
        }
        targets = [r for r in rows if r["week_start_date"] == WEEK]
        if not targets:
            raise ValueError(
                "No October 26–November 1 reports found; nothing was changed"
            )
        plans, updates = [], []
        for row in targets:
            plan, patched = plan_report(row, baselines.get(row["ward_id"]))
            plans.append(plan)
            if plan["status"] == "update":
                updates.append((row, patched))
        counts = dict(Counter(p["status"] for p in plans))
        artifact = save_artifact(
            output_dir,
            {
                "purpose": "oct26_previous_counts",
                "mode": "pre_write_backup" if write else "preview",
                "table": table,
                "target": target,
                "week_start": WEEK,
                "baseline_week_start": BASELINE_WEEK,
                "counts": counts,
                "plans": plans,
                # Full original rows, including both weeks, allow operator recovery.
                "original_rows": [dict(row) for row in rows],
            },
        )
        print(
            json.dumps({"target": target, "artifact": str(artifact), "counts": counts}),
            flush=True,
        )
        for plan in plans:
            if plan["status"] not in ("update", "unchanged"):
                print(
                    json.dumps(
                        {
                            "target": target,
                            "ward_id": plan["ward_id"],
                            "status": plan["status"],
                        }
                    ),
                    flush=True,
                )
        if write:
            for row, patched in updates:
                original = row["report_data"]
                original = (
                    original if isinstance(original, str) else json.dumps(original)
                )
                outcome = await connection.execute(
                    UPDATE.format(table=table),
                    row["ward_id"],
                    WEEK,
                    json.dumps(patched, ensure_ascii=False, allow_nan=False),
                    original,
                )
                if outcome != "UPDATE 1":
                    raise ValueError("Unexpected update count; transaction rolled back")
            verified = {
                row["ward_id"]: row
                for row in await connection.fetch(
                    SELECT.format(table=table), BASELINE_WEEK, WEEK
                )
                if row["week_start_date"] == WEEK
            }
            for row, patched in updates:
                if document(verified[row["ward_id"]], WEEK) != patched:
                    raise ValueError("Verification failed; transaction rolled back")
    # Printed only after transaction commit succeeds.
    skipped = sum(
        n for status, n in counts.items() if status not in ("update", "unchanged")
    )
    print(
        json.dumps(
            {
                "target": target,
                "mode": "committed" if write else "preview",
                "reports": len(targets),
                "updated" if write else "would_update": len(updates),
                "skipped": skipped,
                "counts": counts,
            }
        ),
        flush=True,
    )
    return 2 if skipped else 0


async def connect(target):
    settings = {"statement_timeout": "60000", "lock_timeout": "5000"}
    if target == "local":
        dsn = os.environ.get("WEEKLY_REPORT_STORAGE_DATABASE_DSN", "").strip()
        dsn = dsn or required("ANSIMK_DATABASE_DSN")
        return await asyncpg.connect(dsn, timeout=15, server_settings=settings)
    if target != "prod":
        raise ValueError("Invalid target")
    return await asyncpg.connect(
        host="127.0.0.1",
        port=int(os.environ.get("LIVE_PROD_TUNNEL_PORT", "15432")),
        database=os.environ.get("LIVE_PROD_DB_NAME", "ansimk"),
        user=required("LIVE_PROD_DB_USER"),
        password=required("LIVE_PROD_DB_PASSWORD"),
        ssl=os.environ.get("LIVE_PROD_DB_SSL", "require"),
        timeout=15,
        server_settings=settings,
    )


async def run(args):
    load_dotenv(ENV_FILE, override=False)
    args.output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    targets = ("local", "prod") if args.target == "both" else (args.target,)
    connections = {}
    try:
        # Verify connectivity to both destinations before starting any correction.
        for target in targets:
            connections[target] = await connect(target)
        status = 0
        for target in targets:
            status = max(
                status,
                await correct(
                    connections[target],
                    target=target,
                    write=args.write,
                    output_dir=args.output_dir / target,
                ),
            )
        return status
    finally:
        for connection in connections.values():
            await connection.close()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=("local", "prod", "both"),
        default="both",
        help="Databases to correct (default: both)",
    )
    parser.add_argument(
        "--write", action="store_true", help="Commit eligible corrections"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=HERE / "backups",
        help="Private preview/backup directory",
    )
    return parser.parse_args(argv)


def main():
    args = parse_args()
    try:
        return asyncio.run(run(args))
    except (ValueError, asyncpg.PostgresError, OSError, TimeoutError) as exc:
        # Database exceptions may contain credentials or report values.
        print(
            f"Correction failed ({type(exc).__name__}); inspect per-target commit receipts.",
            file=sys.stderr,
        )
        print(
            "Targets commit independently. Run preview before retrying.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
