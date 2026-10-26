import json
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
        "discovered_count": 3,
        "completed_count": 3 if status == "completed" else 0,
        "failed_count": 0,
        "pending_count": 0,
        "running_count": 0,
        "producer_done": status == "completed",
        "selection_truncated": False,
        "next_cursor": None,
    }


def test_waits_through_finalizing_and_transient_outage():
    terminal = "completed"
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


@pytest.mark.parametrize("status", ["partial", "failed", "cancelled", "cancelling", "expired"])
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


def test_generation_logs_latest_counts_every_five_seconds_including_outage(capsys):
    running = {**job("running"), "completed_count": 1, "pending_count": 1,
               "running_count": 1, "private_data": "must not be logged"}
    responses = iter([URLError("offline"), running, job("completed")])
    now = [0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    def opener(*args, **kwargs):
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        response = FakeResponse(result)
        response.status = 200
        return response

    result = pipeline.wait_for_storage(
        SchedulerSettings(), job(), opener=opener,
        sleeper=sleep, clock=lambda: now[0],
    )
    assert result["status"] == "completed"
    assert sleeps == [5, 5, 5]
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(events) == 3
    assert all(event["event"] == "weekly_report_schedule_progress" for event in events)
    assert all(event["job_id"] == job()["job_id"] for event in events)
    assert [event["completed_count"] for event in events] == [0, 0, 1]
    assert events[-1]["pending_count"] == events[-1]["running_count"] == 1
    assert all(event["timestamp"] and "private_data" not in event for event in events)


def test_failed_job_logs_identity_and_counts(capsys):
    with pytest.raises(ScheduledSubmissionError):
        pipeline.wait_for_storage(SchedulerSettings(), job("failed"))
    event = json.loads(capsys.readouterr().out)
    assert event["event"] == "weekly_report_schedule_job_failed"
    assert event["job_id"] == job()["job_id"]
    assert event["stage"] == "generation"
    assert event["completed_count"] == 0
    assert event["timestamp"]


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

    def wait(settings, submitted, **kwargs):
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


@pytest.mark.parametrize("changes", [
    {"completed_count": 2}, {"failed_count": 1}, {"pending_count": 1},
    {"running_count": 1}, {"producer_done": False}, {"completed_count": None},
    {"selection_truncated": True, "next_cursor": None},
    {"next_cursor": "unacknowledged-continuation"},
])
def test_completed_status_with_missing_reports_cannot_migrate(changes, tmp_path):
    migrate = Mock()
    with pytest.raises(ScheduledSubmissionError):
        pipeline.run_pipeline(
            SchedulerSettings(), state_root=tmp_path,
            submit=lambda *a, **kw: {**job("completed"), **changes},
            migrate=migrate,
        )
    migrate.assert_not_called()
    assert not list(tmp_path.glob("*.json"))


def test_scheduler_follows_all_batches_before_migrating_and_records_total(tmp_path):
    first = {
        **job("completed"), "selection_truncated": True, "next_cursor": "page-two",
        "completed_count": 10_000, "discovered_count": 10_000,
    }
    last = {**job("completed"), "job_id": "9ff04888-a682-4704-8d27-3d5cd2cb26cb"}
    cursors = []

    def submit(*args, **kwargs):
        cursors.append(kwargs["cursor"])
        return last if kwargs["cursor"] else first

    def migrate(week):
        assert cursors == [None, "page-two"]

    pipeline.run_pipeline(
        SchedulerSettings(), now=datetime(2026, 9, 6, 18, tzinfo=UTC),
        state_root=tmp_path, submit=submit, migrate=migrate,
    )
    receipt = json.loads((tmp_path / "2026-08-31.json").read_text())
    assert receipt["report_count"] == 10_003
    assert receipt["job_ids"] == [first["job_id"], last["job_id"]]
    assert receipt["selection_policy"] == pipeline.SELECTION_POLICY


def test_failure_in_later_batch_prevents_migration_and_receipt(tmp_path):
    first = {**job("completed"), "selection_truncated": True, "next_cursor": "page-two"}
    submit = Mock(side_effect=[first, job("failed")])
    migrate = Mock()
    with pytest.raises(ScheduledSubmissionError):
        pipeline.run_pipeline(
            SchedulerSettings(), state_root=tmp_path, submit=submit, migrate=migrate,
        )
    migrate.assert_not_called()
    assert not list(tmp_path.glob("*.json"))


def test_old_receipt_does_not_suppress_all_ward_generation(tmp_path):
    path = tmp_path / "2026-08-31.json"
    path.write_text(json.dumps({"job_id": job()["job_id"], "week_start": "2026-08-31"}))
    submit = Mock(return_value=job("completed"))
    migrate = Mock()
    pipeline.run_pipeline(
        SchedulerSettings(), now=datetime(2026, 9, 6, 18, tzinfo=UTC),
        state_root=tmp_path, submit=submit, migrate=migrate,
    )
    submit.assert_called_once()
    migrate.assert_called_once_with("2026-08-31")
    assert json.loads(path.read_text())["selection_policy"] == pipeline.SELECTION_POLICY


def test_regeneration_bypasses_old_receipt_and_preserves_it_across_all_batches(tmp_path):
    original = tmp_path / "2026-08-31.json"
    old_receipt = json.dumps({"selection_policy": pipeline.SELECTION_POLICY, "old": True})
    original.write_text(old_receipt)
    first = {**job("completed"), "selection_truncated": True, "next_cursor": "page-two"}
    last = {**job("completed"), "job_id": "9ff04888-a682-4704-8d27-3d5cd2cb26cb"}
    submit = Mock(side_effect=[first, last])
    migrate = Mock()
    kwargs = {
        "now": datetime(2026, 9, 6, 18, tzinfo=UTC), "state_root": tmp_path,
        "regeneration_key": "ansimk-v1", "submit": submit, "migrate": migrate,
    }
    pipeline.run_pipeline(SchedulerSettings(), **kwargs)
    pipeline.run_pipeline(SchedulerSettings(), **kwargs)
    assert submit.call_count == 2
    assert [call.kwargs["cursor"] for call in submit.call_args_list] == [None, "page-two"]
    assert all(call.kwargs["regeneration_key"] == "ansimk-v1"
               for call in submit.call_args_list)
    migrate.assert_called_once_with("2026-08-31")
    assert original.read_text() == old_receipt
    receipt = json.loads(
        (tmp_path / "regenerations/ansimk-v1/2026-08-31.json").read_text()
    )
    assert receipt["job_ids"] == [first["job_id"], last["job_id"]]
    assert receipt["report_count"] == 6


def test_regeneration_resumes_migration_with_same_key_after_failure(tmp_path):
    submit = Mock(return_value=job("completed"))
    migrate = Mock(side_effect=[ScheduledSubmissionError("migration failed"), None])
    kwargs = {
        "now": datetime(2026, 9, 6, 18, tzinfo=UTC), "state_root": tmp_path,
        "regeneration_key": "ansimk-v1", "submit": submit, "migrate": migrate,
    }
    receipt = tmp_path / "regenerations/ansimk-v1/2026-08-31.json"
    with pytest.raises(ScheduledSubmissionError):
        pipeline.run_pipeline(SchedulerSettings(), **kwargs)
    assert not receipt.exists()
    pipeline.run_pipeline(SchedulerSettings(), **kwargs)
    assert receipt.exists()
    assert submit.call_args_list[0] == submit.call_args_list[1]


def test_regeneration_failed_batch_cannot_migrate(tmp_path):
    migrate = Mock()
    with pytest.raises(ScheduledSubmissionError):
        pipeline.run_pipeline(
            SchedulerSettings(), state_root=tmp_path, regeneration_key="ansimk-v1",
            submit=Mock(return_value=job("failed")), migrate=migrate,
        )
    migrate.assert_not_called()
    assert not list((tmp_path / "regenerations").rglob("*.json"))


@pytest.mark.parametrize("key", ["../escape", "", "/tmp/escape", "x" * 33])
def test_regeneration_rejects_unsafe_keys_before_submission(key, tmp_path):
    submit = Mock()
    with pytest.raises(ValueError, match="regeneration key"):
        pipeline.run_pipeline(
            SchedulerSettings(), state_root=tmp_path, regeneration_key=key, submit=submit,
        )
    submit.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_regeneration_cli_selects_exact_week_and_key(monkeypatch):
    run = Mock()
    monkeypatch.setattr(pipeline, "run_pipeline", run)
    monkeypatch.setattr(pipeline.sys, "argv", [
        "pipeline", "--week-start", "2026-10-05", "--regenerate", "ansimk-v1",
    ])
    assert pipeline.main() == 0
    assert run.call_args.kwargs["regeneration_key"] == "ansimk-v1"
    assert pipeline.previous_completed_week_start(run.call_args.kwargs["now"]).isoformat() == (
        "2026-10-05"
    )


def test_regeneration_cli_requires_explicit_week(monkeypatch):
    run = Mock()
    monkeypatch.setattr(pipeline, "run_pipeline", run)
    monkeypatch.setattr(pipeline.sys, "argv", ["pipeline", "--regenerate", "ansimk-v1"])
    with pytest.raises(SystemExit) as exc:
        pipeline.main()
    assert exc.value.code == 2
    run.assert_not_called()
