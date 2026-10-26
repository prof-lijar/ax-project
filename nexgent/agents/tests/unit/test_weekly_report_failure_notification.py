import fcntl
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from apps.weekly_report_scheduler import monitor, pipeline
from apps.weekly_report_scheduler.notification import NotificationSettings, write_state
from apps.weekly_report_scheduler.status import RunStatus
from apps.weekly_report_scheduler.submit import (
    ScheduledSubmissionError,
    SchedulerSettings,
)
from tests.unit.test_weekly_report_schedule_pipeline import job
from workflows.weekly_report.failure_notification import failure_payload

NOW = datetime(2026, 9, 27, 19, tzinfo=UTC)  # Monday 04:00 in Korea
SETTINGS = NotificationSettings(True, "http://backend:8000", "x" * 32, "default")
ACCEPTED = {"id": "8ff04888-a682-4704-8d27-3d5cd2cb26cb", "status": "queued"}


def read_run(root):
    return json.loads(next((root / "runs").glob("*.json")).read_text())


@pytest.mark.parametrize("stage", ["submission", "generation", "migration", "notification"])
def test_failed_stage_alert_is_durable_and_preserves_original_error(stage, tmp_path):
    send = Mock(return_value=ACCEPTED)
    failure = Mock(side_effect=lambda record, root: monitor.notify_failure(
        record, root, settings=SETTINGS, now=NOW, send=send
    ))
    actions = {
        "submit": Mock(return_value=job("completed")),
        "wait": Mock(return_value=job("completed")),
        "migrate": Mock(), "notify": Mock(),
    }
    selected = {"submission": "submit", "generation": "wait",
                "migration": "migrate", "notification": "notify"}[stage]
    actions[selected].side_effect = RuntimeError("secret-db-password")
    with pytest.raises(RuntimeError, match="secret-db-password"):
        pipeline.run_pipeline(SchedulerSettings(), state_root=tmp_path, now=NOW,
                              failure_notify=failure, **actions)
    record = read_run(tmp_path)
    assert record["status"] == "failed" and record["stage"] == stage
    assert "secret-db-password" not in json.dumps(record)
    payload = send.call_args.args[1]["payload"]
    assert payload["severity"] == "error"
    assert "secret-db-password" not in json.dumps(payload)
    assert (tmp_path / "2026-09-21.json").exists() == (stage == "notification")
    if stage in {"submission", "generation"}:
        actions["migrate"].assert_not_called()
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW, send=send)
    send.assert_called_once()  # monitor/main observe the same incident


@pytest.mark.parametrize("status", ["failed", "partial", "cancelled", "expired"])
def test_terminal_job_keeps_last_batch_counts(status, tmp_path):
    failed_job = {**job(status), "failed_count": 2, "completed_count": 1}
    failure = Mock()
    with pytest.raises(ScheduledSubmissionError):
        pipeline.run_pipeline(SchedulerSettings(), state_root=tmp_path, now=NOW,
                              submit=lambda *a, **kw: failed_job, failure_notify=failure)
    record = read_run(tmp_path)
    assert record["job"]["failed_count"] == 2
    assert record["job"]["status"] == status
    assert failure.call_args.args[0] == record


def test_configuration_failure_is_tracked(tmp_path, monkeypatch):
    monkeypatch.setattr(SchedulerSettings, "from_env", Mock(side_effect=ValueError("secret")))
    failure = Mock()
    with pytest.raises(ValueError):
        pipeline.run_pipeline(state_root=tmp_path, now=NOW, failure_notify=failure)
    assert read_run(tmp_path)["stage"] == "configuration"
    failure.assert_called_once()


@pytest.mark.parametrize("exc", [SystemExit(143), KeyboardInterrupt()])
def test_process_termination_records_failure_and_keeps_exit_status(tmp_path, exc):
    failure = Mock(side_effect=OSError("backend offline"))
    with pytest.raises(type(exc)) as raised:
        pipeline.run_pipeline(SchedulerSettings(), state_root=tmp_path, now=NOW,
                              submit=Mock(side_effect=exc), failure_notify=failure)
    assert raised.value is exc
    assert read_run(tmp_path)["reason"] == "terminated"


def test_success_never_creates_failure_alert(tmp_path):
    failure = Mock()
    pipeline.run_pipeline(SchedulerSettings(), state_root=tmp_path, now=NOW,
                          submit=lambda *a, **kw: job("completed"), migrate=Mock(),
                          failure_notify=failure)
    assert read_run(tmp_path)["status"] == "succeeded"
    send = Mock()
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW + timedelta(hours=30), send=send)
    failure.assert_not_called()
    send.assert_not_called()


def test_stale_heartbeat_alert_has_last_stage_and_sends_once(tmp_path):
    run = RunStatus(tmp_path, "2026-09-21", clock=lambda: NOW)
    run.update(stage="migration", job=job("completed"))
    send = Mock(return_value=ACCEPTED)
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW + timedelta(seconds=299), send=send)
    send.assert_not_called()
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW + timedelta(seconds=300), send=send)
    assert "스케줄러 응답 없음" in send.call_args.args[1]["payload"]["text"]
    assert "운영 DB 업데이트" in send.call_args.args[1]["payload"]["text"]
    run.update(status="failed", reason="terminated")
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW + timedelta(minutes=10), send=send)
    send.assert_called_once()


def test_fresh_heartbeat_does_not_hide_excessive_runtime(tmp_path):
    run = RunStatus(tmp_path, "2026-09-21", clock=lambda: NOW)
    later = NOW + timedelta(hours=27)
    run.clock = lambda: later
    run.update(stage="generation")
    send = Mock(return_value=ACCEPTED)
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=later, send=send)
    assert "27시간" in send.call_args.args[1]["payload"]["text"]


def test_missed_start_grace_and_monitor_restart(tmp_path):
    send = Mock(return_value=ACCEPTED)
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW - timedelta(hours=4), send=send)
    # The former 01:15 KST deadline must no longer trigger a missed-start alert.
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW - timedelta(hours=2, minutes=45), send=send)
    send.assert_not_called()
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW + timedelta(minutes=14), send=send)
    send.assert_not_called()
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW + timedelta(minutes=15), send=send)
    assert "예약 실행 누락" in send.call_args.args[1]["payload"]["text"]
    assert "월요일 04:00" in send.call_args.args[1]["payload"]["text"]
    assert "2026/09/21 ~ 09/27" in send.call_args.args[1]["payload"]["text"]
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW + timedelta(days=1), send=send)
    send.assert_called_once()


def test_first_install_does_not_alert_for_past_schedules(tmp_path):
    send = Mock()
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW + timedelta(days=1), send=send)
    send.assert_not_called()


def test_monitor_recovers_missed_week_after_downtime(tmp_path):
    send = Mock(return_value=ACCEPTED)
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW - timedelta(minutes=1), send=send)
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW + timedelta(days=8), send=send)
    assert len(list((tmp_path / "alerts").glob("*.json"))) == 2


def test_legacy_migration_receipt_suppresses_false_missed_run(tmp_path):
    send = Mock()
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW - timedelta(minutes=1), send=send)
    write_state(tmp_path / "2026-09-21.json", {"selection_policy": "all-wards-v1"})
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW + timedelta(minutes=15), send=send)
    send.assert_not_called()


def test_outage_retries_frozen_payload_without_restarting_work(tmp_path):
    run = RunStatus(tmp_path, "2026-09-21", clock=lambda: NOW)
    run.update(stage="generation", status="failed", reason="error", job=job("failed"))
    calls = []

    def send(settings, event):
        calls.append((event["key"], json.dumps(event["payload"], sort_keys=True)))
        if len(calls) == 1:
            raise OSError("offline")
        return ACCEPTED

    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW, send=send)
    run.update(job=job("completed"))
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW + timedelta(seconds=29), send=send)
    assert len(calls) == 1
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW + timedelta(seconds=30), send=send)
    assert calls[0] == calls[1]
    event = json.loads(next((tmp_path / "alerts").glob("*.json")).read_text())
    assert event["accepted"] == ACCEPTED


def test_disabled_notifications_and_unsafe_job_fields(tmp_path):
    run = RunStatus(tmp_path, "2026-09-21", clock=lambda: NOW)
    run.update(status="failed", job={"job_id": "secret", "status": "secret",
                                    "error": "secret", "failed_count": "secret"})
    assert "secret" not in run.path.read_text()
    send = Mock()
    monitor.monitor_once(tmp_path, settings=NotificationSettings(), now=NOW, send=send)
    monitor.notify_failure(run.record, tmp_path, settings=NotificationSettings(), send=send)
    send.assert_not_called()


def test_failure_copy_distinguishes_notification_failure_from_storage_failure():
    record = {"week_start": "2026-09-21", "stage": "notification", "reason": "error"}
    text = failure_payload(record, observed_at=NOW.isoformat(), destination="default")["text"]
    assert "운영 DB 업데이트는 완료됐으나" in text
    assert "2026/09/28 04:00:00" in text


def test_outbox_lock_defers_competing_sender_until_next_monitor_tick(tmp_path):
    run = RunStatus(tmp_path, "2026-09-21", clock=lambda: NOW)
    run.update(status="failed")
    send = Mock(return_value=ACCEPTED)
    with (tmp_path / "alerts.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monitor.notify_failure(run.record, tmp_path, settings=SETTINGS, now=NOW, send=send)
        send.assert_not_called()
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW, send=send)
    send.assert_called_once()


def test_crash_after_backend_acceptance_replays_same_key_and_body(tmp_path, monkeypatch):
    run = RunStatus(tmp_path, "2026-09-21", clock=lambda: NOW)
    run.update(status="failed")
    calls = []

    def send(settings, event):
        calls.append((event["key"], json.dumps(event["payload"], sort_keys=True)))
        return ACCEPTED

    def crash_on_ack(path, event):
        if event.get("accepted"):
            raise OSError("disk temporarily unavailable")
        write_state(path, event)

    monkeypatch.setattr(monitor, "write_state", crash_on_ack)
    with pytest.raises(OSError):
        monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW, send=send)
    monkeypatch.setattr(monitor, "write_state", write_state)
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW, send=send)
    assert calls[0] == calls[1]


def test_pending_event_never_switches_backend(tmp_path):
    run = RunStatus(tmp_path, "2026-09-21", clock=lambda: NOW)
    run.update(status="failed")
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW,
                         send=Mock(side_effect=OSError("offline")))
    send = Mock()
    monitor.monitor_once(
        tmp_path, settings=NotificationSettings(True, "http://different:8000", "x" * 32),
        now=NOW + timedelta(minutes=1), send=send,
    )
    send.assert_not_called()


def test_corrupt_run_does_not_block_missed_start_alert(tmp_path):
    send = Mock(return_value=ACCEPTED)
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW - timedelta(minutes=1), send=send)
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "broken.json").write_text("null")
    monitor.monitor_once(tmp_path, settings=SETTINGS, now=NOW + timedelta(minutes=15), send=send)
    send.assert_called_once()
