"""Durable attempt status, independent of notification delivery and report data."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from uuid import UUID, uuid4

from apps.weekly_report_scheduler.notification import write_state


def utc_now():
    return datetime.now(UTC)


class RunStatus:
    def __init__(self, root, week_start, *, clock=utc_now, interval=30):
        self.clock = clock
        self.interval = interval
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None
        self.record = {
            "version": 1,
            "run_id": str(uuid4()),
            "week_start": week_start,
            "status": "running",
            "stage": "configuration",
            "started_at": clock().isoformat(),
        }
        directory = root / "runs"
        directory.mkdir(exist_ok=True)
        self.path = directory / f"{week_start}.{self.record['run_id']}.json"

    def update(self, *, stage=None, status=None, job=None, reason=None):
        with self.lock:
            if stage:
                self.record["stage"] = stage
            if status:
                self.record["status"] = status
            if reason:
                self.record["reason"] = reason
            if job:
                # Only validated operational fields; never copy backend error text.
                safe = {}
                try:
                    safe["job_id"] = str(UUID(job.get("job_id", "")))
                except (ValueError, TypeError, AttributeError):
                    pass
                if job.get("status") in {
                    "pending", "queued", "running", "finalizing", "completed", "partial", "failed",
                    "cancelled", "expired", "cancelling",
                }:
                    safe["status"] = job["status"]
                for key in ("discovered_count", "completed_count", "failed_count",
                            "pending_count", "running_count"):
                    value = job.get(key)
                    if type(value) is int and value >= 0:
                        safe[key] = value
                self.record["job"] = safe
            self.record["heartbeat_at"] = self.clock().isoformat()
            write_state(self.path, self.record)

    def start(self):
        self.update()
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.thread.start()

    def _heartbeat(self):
        while not self.stop.wait(self.interval):
            try:
                self.update()
            except OSError:
                # A stale heartbeat is itself observable by the monitor.
                return

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
