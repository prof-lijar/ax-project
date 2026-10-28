"""Recalculate legacy guardian template IDs in saved reports; preview by default."""

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
from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workflows.weekly_report.domain.activity_policy import ActivityAssessment, _classify
from workflows.weekly_report.domain.device_reception_policy import _COPY as DEVICE_COPY
from workflows.weekly_report.domain.environment_policy import _COPY as ENVIRONMENT_COPY
from workflows.weekly_report.domain.guardian_guidance_policy import (
    select_guardian_guides,
)
from workflows.weekly_report.domain.risk_score_policy import assess_risk_score

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE.parent.parent / ".env"
TABLES = {
    "local": "archive.resources_ward_weekly_report",
    "live": "ansimk.resources_ward_weekly_report",
}


class InvalidReport(ValueError):
    """A fixed, non-sensitive reason for leaving a report unchanged."""


def number(value, *, nullable=False):
    if value is None and nullable:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise InvalidReport("invalid_numeric_evidence")
    return value


def assessed_conditions(data):
    """Recover saved conditions without inventing omitted daily sensor counts."""
    signals = []
    for key in ("activity_detection", "remote_control_usage"):
        section = data["living_activity"][key]
        metrics = section["metrics"]
        assessment = _classify(
            number(metrics["current_week"], nullable=True),
            number(metrics["previous_week"], nullable=True),
        )
        label = "자료 없음" if assessment.status == "UNAVAILABLE" else assessment.status
        if section["status"] != label:
            raise InvalidReport("activity_status_conflicts_with_totals")
        signals.append(assessment)

    environment = data["indoor_environment"]
    if environment["status"] == "자료 없음":
        env_status, env_variant = "UNAVAILABLE", None
    else:
        matches = [
            key
            for key, (_, tag) in ENVIRONMENT_COPY.items()
            if key[0] == environment["status"] and tag == environment["tag"]
        ]
        if len(matches) != 1:
            raise InvalidReport("unrecognized_environment_condition")
        env_status, env_variant = matches[0]

    device = data["device_status"]
    device_statuses = {
        "device_no_data": "자료 없음",
        "unavailable": "판정 불가",
        "device_good": "GOOD",
        "device_power": "CAUTION",
        "device_position": "CAUTION",
    }
    matches = [
        kind
        for kind, (_, tag) in DEVICE_COPY.items()
        if device_statuses[kind] == device["status"] and tag == device["tag"]
    ]
    if len(matches) != 1:
        raise InvalidReport("unrecognized_device_condition")
    device_kind = matches[0]
    device_status = (
        "UNAVAILABLE"
        if device_kind in {"device_no_data", "unavailable"}
        else device["status"]
    )
    if device_kind == "device_no_data":
        metrics = device["metrics"]
        if metrics["current_covered_days"] != 0 or metrics["current_device_count"] != 0:
            raise InvalidReport("no_data_condition_conflicts_with_counts")

    score = number(data["basic_info"]["risk_score"], nullable=True)
    assessment = assess_risk_score(score)
    if score is not None and assessment.status == "UNAVAILABLE":
        raise InvalidReport("invalid_risk_score")
    detected = number(data["risk_management"]["metrics"]["detected_count"])
    if int(detected) != detected:
        raise InvalidReport("invalid_risk_count")
    return {
        "activity": ActivityAssessment(movement=signals[0], remote_control=signals[1]),
        "environment_status": env_status,
        "environment_variant": env_variant,
        "reception_status": device_status,
        "reception_kind": device_kind,
        "risk_score_status": assessment.status,
        "risk_detected_count": int(detected),
    }


def plan_report(data):
    """Change only non-GUI string IDs, after independently selecting current cards."""
    try:
        if (
            not isinstance(data, dict)
            or data.get("template_version") != "weekly-report-v5"
        ):
            raise InvalidReport("unsupported_report_version")
        actions = data["guardian_actions"]
        items = actions["items"]
        if not isinstance(items, list) or any(
            not isinstance(item, dict) for item in items
        ):
            raise InvalidReport("invalid_action_items")
        parent_id = actions.get("template_id")
        if parent_id is not None and (
            not isinstance(parent_id, str) or not parent_id.startswith("GUI_")
        ):
            raise InvalidReport("unexpected_parent_template_id")
        indexes = []
        for index, item in enumerate(items):
            old_id = item.get("template_id")
            if old_id is not None and not isinstance(old_id, str):
                raise InvalidReport("invalid_template_id_type")
            if isinstance(old_id, str) and not old_id.startswith("GUI_"):
                indexes.append(index)
        if not indexes:
            return {"status": "unchanged", "changes": []}, None
        guides = select_guardian_guides(**assessed_conditions(data))
        patched = copy.deepcopy(data)
        changes = []
        for index in indexes:
            item = items[index]
            # The old ID is not used to choose the replacement. Match the card's
            # meaning to a guide that actually passed the current selection rules.
            matches = [
                guide
                for guide in guides
                if guide.title == item["title"] and guide.tag == item["tag"]
            ]
            if len(matches) != 1 or matches[0].template_id is None:
                raise InvalidReport("action_not_selected_by_current_policy")
            template_id = matches[0].template_id
            if not template_id.startswith("GUI_"):
                raise InvalidReport("current_policy_id_not_gui")
            patched["guardian_actions"]["items"][index]["template_id"] = template_id
            changes.append(
                {
                    "item_index": index,
                    "before": item["template_id"],
                    "after": template_id,
                }
            )
        return {"status": "update", "changes": changes}, patched
    except InvalidReport as exc:
        return {"status": "blocked", "reason": str(exc)}, None
    except (KeyError, TypeError, ValueError, OverflowError):
        return {"status": "blocked", "reason": "invalid_report_structure"}, None


def private_artifact(directory, target):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{stamp}-{target}-{uuid4().hex}.jsonl"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return path, os.fdopen(fd, "w", encoding="utf-8")


def record(file, payload):
    file.write(
        json.dumps(payload, ensure_ascii=False, default=str, allow_nan=False) + "\n"
    )


def durable(file, directory):
    file.flush()
    os.fsync(file.fileno())
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


async def migrate(
    connection, *, target, write=False, week_start=None, output_dir=HERE / "backups"
):
    """Plan a snapshot, fsync its backup, then apply guarded updates atomically."""
    table = TABLES[target]  # SQL identifiers are a closed allowlist.
    path, artifact = private_artifact(output_dir, target)
    counts = Counter()
    try:
        record(
            artifact,
            {
                "type": "header",
                "target": target,
                "table": table,
                "mode": "pre_write_backup" if write else "preview",
                "week_start": week_start,
            },
        )
        async with connection.transaction(
            isolation="repeatable_read", readonly=not write
        ):
            query = f"SELECT id, ward_id, week_start_date, week_end_date, report_data, updated_at FROM {table}"
            args = []
            if week_start is not None:
                query += " WHERE week_start_date=$1"
                args.append(week_start)
            query += " ORDER BY id" + (" FOR UPDATE" if write else "")
            async for row in connection.cursor(query, *args, prefetch=250):
                counts["reports"] += 1
                try:
                    data = (
                        json.loads(row["report_data"])
                        if isinstance(row["report_data"], str)
                        else row["report_data"]
                    )
                    period = data["basic_info"]["period"]
                    if (
                        row["week_start_date"].weekday() != 0
                        or row["week_end_date"]
                        != row["week_start_date"] + timedelta(days=6)
                        or period["start_date"] != row["week_start_date"].isoformat()
                        or period["end_date"] != row["week_end_date"].isoformat()
                    ):
                        raise ValueError
                    plan, patched = plan_report(data)
                except (KeyError, TypeError, ValueError):
                    plan, patched = (
                        {"status": "blocked", "reason": "invalid_report_or_period"},
                        None,
                    )
                counts[plan["status"]] += 1
                if plan["status"] == "unchanged":
                    continue
                entry = {
                    "type": "plan",
                    "id": row["id"],
                    "ward_id": row["ward_id"],
                    "week_start_date": row["week_start_date"],
                    **plan,
                }
                if patched is not None:
                    entry.update(original_row=dict(row), patched_report_data=patched)
                record(artifact, entry)
            record(artifact, {"type": "planned", "counts": dict(counts)})
            durable(artifact, output_dir)
            print(
                json.dumps(
                    {"target": target, "artifact": str(path), "counts": dict(counts)}
                ),
                flush=True,
            )
            # A conflict must be reviewed before a partial migration can be mistaken
            # for completion. Preview remains useful; write commits no rows if blocked.
            if write and counts["blocked"]:
                raise ValueError(
                    "Blocked reports exist; no updates applied to this target"
                )
            if write:
                with path.open(encoding="utf-8") as backup:
                    for line in backup:
                        entry = json.loads(line)
                        if entry.get("status") != "update":
                            continue
                        original = entry["original_row"]["report_data"]
                        original = (
                            original
                            if isinstance(original, str)
                            else json.dumps(original, ensure_ascii=False)
                        )
                        outcome = await connection.execute(
                            f"UPDATE {table} SET report_data=$2::jsonb, updated_at=NOW() "
                            "WHERE id=$1 AND ward_id=$3 AND report_data=$4::jsonb",
                            entry["id"],
                            json.dumps(
                                entry["patched_report_data"],
                                ensure_ascii=False,
                                allow_nan=False,
                            ),
                            entry["ward_id"],
                            original,
                        )
                        if outcome != "UPDATE 1":
                            raise ValueError(
                                "Concurrent change or unexpected update count; rolling back target"
                            )
        # This receipt is written only after the transaction has completed.
        result = {
            "type": "result",
            "target": target,
            "mode": "committed" if write else "preview",
            "reports": counts["reports"],
            "updated" if write else "would_update": counts["update"],
            "blocked": counts["blocked"],
            "unchanged": counts["unchanged"],
        }
        record(artifact, result)
        durable(artifact, output_dir)
        print(json.dumps(result), flush=True)
        return 2 if counts["blocked"] else 0
    finally:
        artifact.close()


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing {name}")
    return value


def local_dsn():
    values = dotenv_values(ROOT / ".env")
    for key in (
        "SOURCE_DATABASE_DSN",
        "WEEKLY_REPORT_STORAGE_DATABASE_DSN",
        "ANSIMK_DATABASE_DSN",
    ):
        value = os.environ.get(key) or (
            values.get(key)
        )
        if value and value.strip():
            return value.strip()
    raise ValueError("Missing local database DSN")


async def run(args):
    load_dotenv(ENV_FILE, override=False)
    targets = ("local", "live") if args.target == "both" else (args.target,)
    result = 0
    settings = {"statement_timeout": "120000", "lock_timeout": "5000"}
    if not args.write:
        settings["default_transaction_read_only"] = "on"
    for target in targets:
        print(json.dumps({"target": target, "stage": "connecting"}), flush=True)
        if target == "local":
            connection = await asyncpg.connect(
                local_dsn(), timeout=15, server_settings=settings
            )
        else:
            connection = await asyncpg.connect(
                host="127.0.0.1",
                port=int(os.environ.get("LIVE_PROD_TUNNEL_PORT", "15432")),
                database=os.environ.get("LIVE_PROD_DB_NAME", "ansimk"),
                user=required("LIVE_PROD_DB_USER"),
                password=required("LIVE_PROD_DB_PASSWORD"),
                ssl=os.environ.get("LIVE_PROD_DB_SSL", "require"),
                timeout=15,
                server_settings=settings,
            )
        try:
            status = await migrate(
                connection,
                target=target,
                write=args.write,
                week_start=args.week_start,
                output_dir=args.output_dir,
            )
            result = max(result, status)
        finally:
            await connection.close()
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("local", "live", "both"), default="local")
    parser.add_argument(
        "--write", action="store_true", help="Commit ID-only updates after backup"
    )
    parser.add_argument(
        "--week-start", type=date.fromisoformat, help="Limit to one Monday YYYY-MM-DD"
    )
    parser.add_argument("--output-dir", type=Path, default=HERE / "backups")
    args = parser.parse_args(argv)
    if args.week_start is not None and args.week_start.weekday() != 0:
        parser.error("--week-start must be a Monday")
    return args


def main():
    args = parse_args()
    try:
        return asyncio.run(run(args))
    except (ValueError, asyncpg.PostgresError, OSError, TimeoutError) as exc:
        # Do not print database exception messages: they may embed report data.
        print(
            json.dumps(
                {
                    "error": type(exc).__name__,
                    "message": "Migration failed; inspect the last target and its artifact. Rerun preview to verify commit state.",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
