"""Independent monitor and durable failure-notification outbox.

No report generation, migration, or production database access happens here.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from apps.weekly_report_scheduler.notification import (
    NotificationSettings,
    send_event,
    write_state,
)
from apps.weekly_report_scheduler.submit import _write_event
from workflows.weekly_report.failure_notification import failure_payload

STATE_ROOT = "/var/lib/ax/weekly-report-scheduler"


def scheduled_due(now):
    local = now.astimezone(ZoneInfo("Asia/Seoul"))
    due = local.replace(hour=4, minute=0, second=0, microsecond=0) - timedelta(
        days=local.weekday()
    )
    if due > local:
        due -= timedelta(days=7)
    return due


def read_state(path):
    return json.loads(path.read_text())


def _queue(root, record, settings, now):
    identity = record.get("run_id") or f"missed-{record['week_start']}"
    path = root / "alerts" / f"{identity}.json"
    if path.exists():
        return
    event = {
        "key": f"weekly-report:failure:{identity}",
        "base_url": settings.base_url,
        "payload": failure_payload(
            record, observed_at=now.isoformat(), destination=settings.destination
        ),
        "attempts": 0,
        "next_attempt_at": now.isoformat(),
    }
    write_state(path, event)


def _dispatch(root, settings, now, send):
    candidates = []
    for path in (root / "alerts").glob("*.json"):
        try:
            event = read_state(path)
            if not event.get("accepted") and datetime.fromisoformat(
                event["next_attempt_at"]
            ) <= now:
                candidates.append((event["next_attempt_at"], path, event))
        except (ValueError, KeyError, TypeError, AttributeError):
            _write_event({"event": "weekly_report_monitor_invalid_alert_state"})
    # One bounded submission per tick; a broken backend cannot starve detection.
    for _, path, event in sorted(candidates)[:1]:
        try:
            if event["base_url"] != settings.base_url:
                raise ValueError("notification backend changed during recovery")
            event["accepted"] = send(settings, event)
        except Exception as exc:  # noqa: BLE001 - preserve outbox on any submission failure
            event["attempts"] += 1
            event["next_attempt_at"] = (now + timedelta(
                seconds=min(300, 30 * 2 ** min(event["attempts"] - 1, 4))
            )).isoformat()
            _write_event({"event": "weekly_report_failure_notification_retry",
                          "error_type": type(exc).__name__})
        write_state(path, event)


def _with_outbox(root, action):
    root.mkdir(parents=True, exist_ok=True)
    (root / "alerts").mkdir(exist_ok=True)
    # Main and monitor serialize creation/ack; backend key survives a crash after send.
    with (root / "alerts.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        action()


def notify_failure(record, root, *, settings=None, now=None, send=send_event):
    settings = settings or NotificationSettings.from_env()
    if not settings.enabled:
        return
    now = now or datetime.now(UTC)

    def action():
        _queue(root, record, settings, now)
        _dispatch(root, settings, now, send)

    _with_outbox(root, action)


def monitor_once(root, *, settings, now=None, send=send_event):
    now = now or datetime.now(UTC)

    def action():
        activation = root / "monitor.json"
        if not activation.exists():
            write_state(activation, {"started_at": now.isoformat()})
        active_since = datetime.fromisoformat(read_state(activation)["started_at"])
        if not settings.enabled:
            return
        records = []
        for path in sorted((root / "runs").glob("*.json")):
            try:
                record = read_state(path)
                if (not isinstance(record, dict)
                        or record.get("status") not in {"running", "failed", "succeeded"}
                        or not isinstance(record.get("week_start"), str)):
                    raise ValueError("invalid attempt record")
                records.append(record)
                if record["status"] == "failed":
                    _queue(root, record, settings, now)
                elif record["status"] == "running":
                    stale = (now - datetime.fromisoformat(record["heartbeat_at"])
                             ).total_seconds() >= 300
                    overdue = (now - datetime.fromisoformat(record["started_at"])
                               ).total_seconds() >= 27 * 3600
                    if stale or overdue:
                        _queue(root, {**record, "reason": "heartbeat" if stale else "overdue"},
                               settings, now)
            except (ValueError, KeyError, TypeError):
                _write_event({"event": "weekly_report_monitor_invalid_run_state"})
        due = scheduled_due(now)
        # Check each due date since activation, including monitor downtime. At most
        # 53 weeks of missed schedules per tick; normal operation is one week.
        earliest = max(active_since, now - timedelta(weeks=53))
        while due >= earliest:
            week = (due.date() - timedelta(days=7)).isoformat()
            receipt = root / f"{week}.json"
            migrated = False
            if receipt.exists():
                try:
                    migrated = read_state(receipt).get("selection_policy") == "all-wards-v1"
                except (ValueError, AttributeError):
                    pass
            if (now >= due + timedelta(minutes=15) and not migrated
                    and not any(r.get("week_start") == week for r in records)):
                _queue(root, {"week_start": week, "stage": "schedule", "reason": "missed"},
                       settings, now)
            due -= timedelta(days=7)
        _dispatch(root, settings, now, send)

    _with_outbox(root, action)


def main():
    root = Path(os.environ.get("WEEKLY_REPORT_SCHEDULE_STATE_ROOT", STATE_ROOT))
    initialized = False
    while True:
        try:
            if not initialized:
                # Record activation even while notification credentials are broken.
                monitor_once(root, settings=NotificationSettings())
                initialized = (root / "monitor.json").exists()
            monitor_once(root, settings=NotificationSettings.from_env())
        except Exception as exc:  # noqa: BLE001 - keep the independent observer alive
            # Configuration/backend/storage outages must not kill the monitor loop.
            _write_event({"event": "weekly_report_monitor_failed",
                          "error_type": type(exc).__name__})
        time.sleep(30)


if __name__ == "__main__":
    main()
