"""Submit, persist, migrate, and notify about the scheduled production week."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from apps.weekly_report_scheduler.submit import (
    MAX_RESPONSE_BYTES,
    SCHEDULE_TIMEZONE,
    ScheduledSubmissionError,
    SchedulerSettings,
    _validate_response,
    _write_event,
    previous_completed_week_start,
    submit_scheduled_job,
)

ROOT = Path(__file__).resolve().parents[2]
SELECTION_POLICY = "all-wards-v1"


def _validate_complete_batch(job):
    counts = [job.get(key) for key in (
        "discovered_count", "completed_count", "failed_count",
        "pending_count", "running_count",
    )]
    if (
        job.get("status") != "completed"
        or job.get("producer_done") is not True
        or any(type(value) is not int or value < 0 for value in counts)
        or counts[0] != counts[1]
        or any(counts[2:])
        or type(job.get("selection_truncated")) is not bool
    ):
        raise ScheduledSubmissionError("scheduled batch is missing ward reports")
    cursor = job.get("next_cursor")
    if job["selection_truncated"]:
        if not isinstance(cursor, str) or not cursor or not counts[0]:
            raise ScheduledSubmissionError("scheduled batch has invalid continuation")
    elif cursor is not None:
        raise ScheduledSubmissionError("scheduled batch has unexpected continuation")


def wait_for_storage(
    settings,
    job,
    *,
    opener=urlopen,
    sleeper=time.sleep,
    clock=time.monotonic,
    wait_seconds=86400,
    poll_seconds=30,
    progress=None,
):
    """Terminal success follows the bulk finalizer's committed storage write."""
    deadline = clock() + wait_seconds
    expected_id = job["job_id"]
    while True:
        if progress:
            progress(job)
        if job["status"] == "completed":
            _validate_complete_batch(job)
            return job
        if job["status"] in {"partial", "failed", "cancelled", "expired", "cancelling"}:
            _write_event({
                "event": "weekly_report_schedule_job_failed",
                "stage": "generation", "job_id": expected_id,
                "week_start": job["week_start"], "job_status": job["status"],
                "discovered_count": job.get("discovered_count"),
                "completed_count": job.get("completed_count"),
                "failed_count": job.get("failed_count"),
                "producer_done": job.get("producer_done"),
            })
            raise ScheduledSubmissionError("scheduled job did not finish local storage")
        if clock() >= deadline:
            raise ScheduledSubmissionError("timed out waiting for local storage")
        sleeper(min(poll_seconds, max(0, deadline - clock())))
        request = Request(
            settings.jobs_url + "/" + expected_id,
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with opener(request, timeout=settings.timeout_seconds) as response:
                if response.status != 200:
                    raise ScheduledSubmissionError("unexpected bulk status response")
                body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError("oversized response")
            updated = _validate_response(body, job)
            if updated["job_id"] != expected_id:
                raise ValueError("wrong job")
            job = updated
        except HTTPError as exc:
            retryable = exc.code in {408, 425, 429} or exc.code >= 500
            exc.close()
            if not retryable:
                raise ScheduledSubmissionError("bulk status request rejected") from None
        except (TimeoutError, URLError):
            continue
        except (ValueError, TypeError, OSError):
            raise ScheduledSubmissionError("invalid bulk status response") from None


def migrate_week(week_start: str) -> None:
    run_database_command(week_start)


def collect_production_coverage(week_start, output):
    run_database_command(week_start, coverage_output=output)


def run_database_command(week_start, *, coverage_output=None):
    # Validate before handing the date to the fixed script; never invoke a shell string.
    selected = date.fromisoformat(week_start)
    if selected.weekday() != 0:
        raise ValueError("migration week must start on Monday")
    command = [
        "bash",
        str(ROOT / "playground/weekly-reporter/migrate.sh"),
    ]
    if coverage_output is None:
        command.append("--write")
    command.extend(["--week-start", selected.isoformat()])
    if coverage_output is not None:
        command.extend(["--coverage-output", str(coverage_output)])
    environment = {**os.environ, "PYTHON_BIN": sys.executable}
    with subprocess.Popen(command, env=environment, start_new_session=True) as process:
        try:
            result = process.wait(timeout=3600)
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    if result != 0:
        raise ScheduledSubmissionError("weekly report migration failed")


def run_pipeline(
    settings=None,
    *,
    now=None,
    state_root=None,
    submit=submit_scheduled_job,
    wait=wait_for_storage,
    migrate=migrate_week,
    notify=None,
    failure_notify=None,
):
    now = datetime.now(UTC) if now is None else now
    week_start = previous_completed_week_start(now).isoformat()
    state_root = Path(
        state_root
        or os.environ.get(
            "WEEKLY_REPORT_SCHEDULE_STATE_ROOT", "/var/lib/ax/weekly-report-scheduler"
        )
    )
    state_root.mkdir(parents=True, exist_ok=True)
    # Serialize all weeks because migrate.sh owns one fixed local SSH port.
    with (state_root / "pipeline.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        from apps.weekly_report_scheduler.status import RunStatus

        status = RunStatus(state_root, week_start)
        try:
            status.start()
            settings = settings or SchedulerSettings.from_env()
            _run_locked(settings, now, state_root, week_start, status, submit, wait,
                        migrate, notify)
            status.update(status="succeeded")
        except BaseException as exc:
            status.close()
            try:
                status.update(status="failed", reason=(
                    "terminated" if isinstance(exc, (SystemExit, KeyboardInterrupt)) else "error"
                ))
                if failure_notify:
                    failure_notify(status.record, state_root)
            except Exception as notification_exc:  # noqa: BLE001 - preserve original failure
                _write_event({"event": "weekly_report_failure_notification_deferred",
                              "error_type": type(notification_exc).__name__})
            raise
        finally:
            status.close()


def _run_locked(settings, now, state_root, week_start, status, submit, wait, migrate, notify):
    receipt = state_root / (week_start + ".json")
    if receipt.exists() and json.loads(receipt.read_text()).get(
        "selection_policy"
    ) == SELECTION_POLICY:
        _write_event(
            {
                "event": "weekly_report_migration_already_completed",
                "week_start": week_start,
            }
        )
        if notify:
            status.update(stage="notification")
            notify(week_start, state_root)
        return
    cursor = None
    seen_cursors = set()
    job_ids = []
    report_count = 0
    deadline = time.monotonic() + 86400
    while True:
        if time.monotonic() >= deadline:
            raise ScheduledSubmissionError("scheduled ward discovery timed out")
        status.update(stage="submission")
        job = submit(settings, now=now, cursor=cursor, log_event=_write_event)
        status.update(stage="generation", job=job)
        progress = {"progress": lambda job: status.update(job=job)} if wait is wait_for_storage else {}
        completed = wait(
            settings, job, wait_seconds=max(0, deadline - time.monotonic()), **progress
        )
        status.update(job=completed)
        _validate_complete_batch(completed)
        if completed["job_id"] in job_ids:
            raise ScheduledSubmissionError("scheduled batch repeated a job")
        job_ids.append(completed["job_id"])
        report_count += completed["completed_count"]
        cursor = completed["next_cursor"]
        if cursor is None:
            break
        if cursor in seen_cursors:
            raise ScheduledSubmissionError("scheduled batch repeated a cursor")
        seen_cursors.add(cursor)
    _write_event(
        {
            "event": "weekly_report_migration_started",
            "job_id": job["job_id"],
            "week_start": week_start,
            "job_status": completed["status"],
        }
    )
    status.update(stage="migration")
    migrate(week_start)
    temporary = receipt.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({
            "job_id": job["job_id"], "job_ids": job_ids,
            "week_start": week_start, "report_count": report_count,
            "selection_policy": SELECTION_POLICY,
        })
    )
    temporary.replace(receipt)
    _write_event(
        {
            "event": "weekly_report_migration_completed",
            "job_id": job["job_id"],
            "week_start": week_start,
        }
    )
    if notify:
        status.update(stage="notification")
        notify(week_start, state_root)


def main() -> int:
    from apps.weekly_report_scheduler.notification import (
        NotificationError,
        NotificationSettings,
        notify_completed_week,
    )

    def stop(_signum, _frame):
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, stop)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--week-start",
        type=date.fromisoformat,
        help="Resume a specific reporting Monday without regenerating its job",
    )
    args = parser.parse_args()
    now = None
    if args.week_start is not None:
        if args.week_start.weekday() != 0:
            parser.error("--week-start must be a Monday")
        now = datetime.combine(
            args.week_start + timedelta(days=7),
            datetime.min.time(),
            tzinfo=ZoneInfo(SCHEDULE_TIMEZONE),
        )
    try:
        def notify(week_start, state_root):
            try:
                settings = NotificationSettings.from_env()
                accepted = notify_completed_week(
                    week_start, state_root, settings=settings,
                    collect=collect_production_coverage,
                )
            except (ValueError, OSError, NotificationError, ScheduledSubmissionError,
                    subprocess.TimeoutExpired) as exc:
                _write_event({
                    "event": "weekly_report_notification_failed",
                    "week_start": week_start, "error_type": type(exc).__name__,
                })
                raise
            _write_event({
                "event": "weekly_report_notification_accepted" if settings.enabled
                else "weekly_report_notification_disabled",
                "week_start": week_start,
                "notification_id": accepted["id"] if accepted else None,
                "notification_status": accepted["status"] if accepted else None,
            })

        from apps.weekly_report_scheduler.monitor import notify_failure

        run_pipeline(now=now, notify=notify, failure_notify=notify_failure)
    except Exception as exc:  # noqa: BLE001 - process boundary logs unexpected failures too
        _write_event(
            {
                "event": "weekly_report_schedule_pipeline_failed",
                "error_type": type(exc).__name__,
            }
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
