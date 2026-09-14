from datetime import UTC, datetime
from unittest.mock import Mock
from urllib.error import URLError

import pytest

from apps.weekly_report_scheduler import pipeline
from apps.weekly_report_scheduler.submit import (
    ScheduledSubmissionError,
    SchedulerSettings,
)
from tests.unit.test_weekly_report_scheduler import FakeResponse


def job(status="pending"):
    return {
        "job_id": "8ff04888-a682-4704-8d27-3d5cd2cb26cb",
        "status": status,
        "week_start": "2026-08-31",
        "timezone": "Asia/Seoul",
        "max_reports": 10000,
    }


@pytest.mark.parametrize("terminal", ["completed", "partial"])
def test_waits_through_finalizing_and_transient_outage(terminal):
    statuses = iter([URLError("offline"), "finalizing", terminal])
    calls = []

    def opener(request, **kwargs):
        calls.append(request)
        status = next(statuses)
        if isinstance(status, Exception):
            raise status
        response = FakeResponse(job(status))
        response.status = 200
        return response

    result = pipeline.wait_for_storage(
        SchedulerSettings(), job(), opener=opener, sleeper=lambda _: None
    )
    assert result["status"] == terminal
    assert len(calls) == 3
    assert all(request.method == "GET" for request in calls)
    assert all(request.full_url.endswith("/" + job()["job_id"]) for request in calls)


@pytest.mark.parametrize("status", ["failed", "cancelled", "cancelling", "expired"])
def test_unsuccessful_job_cannot_trigger_migration(status, tmp_path):
    migrate = Mock()
    with pytest.raises(ScheduledSubmissionError):
        pipeline.run_pipeline(
            SchedulerSettings(),
            state_root=tmp_path,
            submit=lambda *a, **kw: job(status),
            migrate=migrate,
        )
    migrate.assert_not_called()
    assert not list(tmp_path.glob("*.json"))


def test_timeout_is_bounded():
    clock = iter([0, 2])
    with pytest.raises(ScheduledSubmissionError, match="timed out"):
        pipeline.wait_for_storage(
            SchedulerSettings(), job(), wait_seconds=1, clock=lambda: next(clock)
        )


@pytest.mark.parametrize(
    "field,value",
    [("week_start", "2026-09-07"), ("job_id", "9ff04888-a682-4704-8d27-3d5cd2cb26cb")],
)
def test_poll_rejects_mismatched_job(field, value):
    response = FakeResponse({**job("completed"), field: value})
    response.status = 200
    with pytest.raises(ScheduledSubmissionError, match="invalid bulk status"):
        pipeline.wait_for_storage(
            SchedulerSettings(),
            job(),
            opener=lambda *a, **kw: response,
            sleeper=lambda _: None,
        )


def test_migration_uses_reporting_monday_after_storage_and_saves_receipt(tmp_path):
    order = []

    def wait(settings, submitted):
        order.append("storage_committed")
        return job("completed")

    def migrate(week):
        order.append(week)

    kwargs = {
        "now": datetime(2026, 9, 6, 18, tzinfo=UTC),
        "state_root": tmp_path,
        "submit": Mock(return_value=job()),
        "wait": wait,
        "migrate": migrate,
    }
    pipeline.run_pipeline(SchedulerSettings(), **kwargs)
    pipeline.run_pipeline(SchedulerSettings(), **kwargs)
    assert order == ["storage_committed", "2026-08-31"]
    kwargs["submit"].assert_called_once()
    assert (tmp_path / "2026-08-31.json").exists()


def test_failed_migration_can_resume_without_success_receipt(tmp_path):
    migrate = Mock(side_effect=[ScheduledSubmissionError("migration failed"), None])
    kwargs = {
        "now": datetime(2026, 9, 6, 18, tzinfo=UTC),
        "state_root": tmp_path,
        "submit": Mock(return_value=job("completed")),
        "migrate": migrate,
    }
    with pytest.raises(ScheduledSubmissionError):
        pipeline.run_pipeline(SchedulerSettings(), **kwargs)
    assert not list(tmp_path.glob("*.json"))
    pipeline.run_pipeline(SchedulerSettings(), **kwargs)
    assert migrate.call_count == 2


def test_migrate_invokes_existing_script_with_write_and_exact_date(monkeypatch):
    process = Mock()
    process.__enter__ = Mock(return_value=process)
    process.__exit__ = Mock(return_value=False)
    process.wait.return_value = 0
    popen = Mock(return_value=process)
    monkeypatch.setattr(pipeline.subprocess, "Popen", popen)
    pipeline.migrate_week("2026-08-31")
    command = popen.call_args.args[0]
    assert command == [
        "bash",
        str(pipeline.ROOT / "playground/weekly-reporter/migrate.sh"),
        "--write",
        "--week-start",
        "2026-08-31",
    ]
    assert popen.call_args.kwargs["env"]["PYTHON_BIN"] == pipeline.sys.executable
    assert popen.call_args.kwargs["start_new_session"] is True


def test_cron_and_image_include_migration():
    root = pipeline.ROOT
    assert (
        "weekly_report_scheduler.pipeline"
        in (root / "apps/weekly_report_scheduler/crontab").read_text()
    )
    dockerfile = (root / "apps/weekly_report_scheduler/Dockerfile").read_text()
    assert "sshpass" in dockerfile
    assert "playground/weekly-reporter/migrate.sh" in dockerfile


@pytest.mark.parametrize(
    "outcome", [1, pipeline.subprocess.TimeoutExpired("migration", 3600)]
)
def test_migration_failure_and_timeout_are_not_success(monkeypatch, outcome):
    process = Mock(pid=12345)
    process.__enter__ = Mock(return_value=process)
    process.__exit__ = Mock(return_value=False)
    if isinstance(outcome, Exception):
        process.wait.side_effect = [outcome, 0]
    else:
        process.wait.return_value = outcome
    monkeypatch.setattr(pipeline.subprocess, "Popen", Mock(return_value=process))
    killpg = Mock()
    monkeypatch.setattr(pipeline.os, "killpg", killpg)
    with pytest.raises((ScheduledSubmissionError, pipeline.subprocess.TimeoutExpired)):
        pipeline.migrate_week("2026-08-31")
    if isinstance(outcome, Exception):
        killpg.assert_called_once_with(12345, pipeline.signal.SIGTERM)


def test_pipeline_lock_prevents_overlapping_tunnels(tmp_path):
    submit = Mock()
    with (tmp_path / "pipeline.lock").open("a") as lock:
        pipeline.fcntl.flock(lock, pipeline.fcntl.LOCK_EX | pipeline.fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            pipeline.run_pipeline(
                SchedulerSettings(), state_root=tmp_path, submit=submit
            )
    submit.assert_not_called()
