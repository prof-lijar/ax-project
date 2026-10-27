import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from apps.daily_risk_scheduler import notification, run
from tests.unit.test_daily_risk_counts import connection_fixture
from workflows.daily_risk_counts.notification import status_payload

DAY = date(2026, 1, 1)
TIMES = {
    "started_at": datetime(2026, 1, 2, 20, 15, tzinfo=UTC),
    "ended_at": datetime(2026, 1, 2, 20, 16, tzinfo=UTC),
}


def configure(tmp_path, monkeypatch, enabled="true"):
    path = tmp_path / "prod.env"
    path.write_text(
        f"NEXGENT_SLACK_ENABLED={enabled}\n"
        f"NEXGENT_NOTIFICATION_SERVICE_TOKEN={'s' * 32}\n"
        'NEXGENT_SLACK_CHANNELS={"daily_risk":"C0C24T2124E"}\n'
    )
    monkeypatch.setattr(notification, "PRODUCTION_NOTIFICATION_ENV", path)


@pytest.mark.asyncio
@pytest.mark.parametrize("apply", [True, False])
async def test_commit_precedes_success_notification_and_preview_is_silent(
    monkeypatch, apply
):
    connection, transaction = connection_fixture()
    stages = []
    transaction.__aexit__.side_effect = lambda *args: stages.append("commit")
    monkeypatch.setattr(run, "database_dsn", lambda: "private")
    monkeypatch.setattr(run.asyncpg, "connect", AsyncMock(return_value=connection))

    async def notify(day, **kwargs):
        assert stages == ["commit"]
        assert "issue" not in kwargs
        assert kwargs["started_at"] <= kwargs["ended_at"]

    sender = AsyncMock(side_effect=notify)
    monkeypatch.setattr(run, "notify_status", sender)
    await run.run(DAY, apply=apply)
    assert sender.await_count == int(apply)


@pytest.mark.parametrize("stage", ["connect", "commit"])
def test_failed_apply_notifies_failure_and_returns_nonzero(monkeypatch, stage, capsys):
    connection, transaction = connection_fixture()
    connector = AsyncMock(return_value=connection)
    if stage == "connect":
        connector.side_effect = RuntimeError("SECRET")
    else:
        transaction.__aexit__.side_effect = RuntimeError("SECRET")
    monkeypatch.setattr(run, "database_dsn", lambda: "private")
    monkeypatch.setattr(run.asyncpg, "connect", connector)
    sender = AsyncMock()
    monkeypatch.setattr(run, "notify_status", sender)
    assert run.main(["--date", DAY.isoformat(), "--apply"]) == 1
    sender.assert_awaited_once()
    assert sender.call_args.args == (DAY,)
    assert sender.call_args.kwargs["started_at"] <= sender.call_args.kwargs["ended_at"]
    assert (
        "Database connection" if stage == "connect" else "Database reconciliation"
    ) in sender.call_args.kwargs["issue"]
    assert "SECRET" not in sender.call_args.kwargs["issue"]
    output = capsys.readouterr().out
    assert "SECRET" not in output and "daily_risk_completed" not in output
    assert output.count('"event": "daily_risk_failed"') == 1


@pytest.mark.asyncio
async def test_cleanup_error_after_commit_still_reports_success(monkeypatch):
    connection, _ = connection_fixture()
    connection.close.side_effect = RuntimeError("SECRET")
    monkeypatch.setattr(run, "database_dsn", lambda: "private")
    monkeypatch.setattr(run.asyncpg, "connect", AsyncMock(return_value=connection))
    sender = AsyncMock()
    monkeypatch.setattr(run, "notify_status", sender)
    await run.run(DAY, apply=True)
    assert "issue" not in sender.call_args.kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [None, RuntimeError("SECRET")])
async def test_backend_submission_and_redacted_failure(tmp_path, monkeypatch, outcome):
    configure(tmp_path, monkeypatch)
    accepted = {"id": "receipt", "status": "queued"}
    send = AsyncMock(return_value=accepted, side_effect=outcome)
    monkeypatch.setattr(notification, "submit_notification", send)
    events = Mock()
    await notification.notify_status(DAY, **TIMES, event=events)
    kwargs = send.call_args.kwargs
    assert kwargs["base_url"] == "http://127.0.0.1:8001"
    assert kwargs["token"] == "s" * 32
    assert kwargs["key"].startswith(f"daily-risk:{DAY}:")
    assert kwargs["payload"]["severity"] == "success"
    assert kwargs["payload"]["destination"] == "daily_risk"
    assert events.call_args.args[0] == (
        "daily_risk_notification_failed"
        if outcome
        else "daily_risk_notification_accepted"
    )
    assert "SECRET" not in str(events.call_args)


@pytest.mark.asyncio
async def test_host_backend_port_override_and_distinct_manual_run_keys(
    tmp_path, monkeypatch
):
    configure(tmp_path, monkeypatch)
    monkeypatch.setenv("DAILY_RISK_NOTIFICATION_BASE_URL", "http://127.0.0.1:9001")
    send = AsyncMock(return_value={"id": "receipt", "status": "queued"})
    monkeypatch.setattr(notification, "submit_notification", send)
    for _ in range(2):
        await notification.notify_status(DAY, **TIMES, event=Mock())
    first, second = [call.kwargs for call in send.call_args_list]
    assert first["base_url"] == "http://127.0.0.1:9001"
    assert first["key"] != second["key"]
    assert first["payload"] == second["payload"]


@pytest.mark.asyncio
async def test_missing_daily_destination_never_falls_back_to_default(
    tmp_path, monkeypatch
):
    configure(tmp_path, monkeypatch)
    path = tmp_path / "prod.env"
    path.write_text(
        path.read_text().replace(
            '"daily_risk":"C0C24T2124E"', '"default":"C0BABHEUTV5"'
        )
    )
    send = AsyncMock()
    monkeypatch.setattr(notification, "submit_notification", send)
    events = Mock()
    await notification.notify_status(DAY, **TIMES, event=events)
    send.assert_not_awaited()
    assert events.call_args.args[0] == "daily_risk_notification_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("config", ["missing", "false", "invalid"])
async def test_missing_disabled_or_invalid_settings_do_not_send(
    tmp_path, monkeypatch, config
):
    configure(tmp_path, monkeypatch, enabled=config)
    if config == "missing":
        (tmp_path / "prod.env").unlink()
    send = AsyncMock()
    monkeypatch.setattr(notification, "submit_notification", send)
    events = Mock()
    await notification.notify_status(DAY, **TIMES, event=events)
    send.assert_not_awaited()
    assert events.call_args.args[0] == (
        "daily_risk_notification_failed"
        if config == "invalid"
        else "daily_risk_notification_disabled"
    )


def test_slack_outage_does_not_change_committed_cli_result(
    tmp_path, monkeypatch, capsys
):
    configure(tmp_path, monkeypatch)
    connection, _ = connection_fixture()
    monkeypatch.setattr(run, "database_dsn", lambda: "private")
    monkeypatch.setattr(run.asyncpg, "connect", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        notification,
        "submit_notification",
        AsyncMock(side_effect=RuntimeError("SECRET")),
    )
    assert run.main(["--date", DAY.isoformat(), "--apply"]) == 0
    output = capsys.readouterr().out
    events = [json.loads(line)["event"] for line in output.splitlines()]
    assert events == [
        "daily_risk_started",
        "daily_risk_completed",
        "daily_risk_notification_failed",
    ]
    assert "SECRET" not in output


def test_success_message_format_and_kst_timestamps():
    payload = status_payload(**TIMES)
    assert payload["destination"] == "daily_risk"
    assert payload["locale"] == "en" and payload["severity"] == "success"
    assert payload["text"] == (
        "Status: Success\nTitle: Daily Risk Count\n"
        "Start time: 2026-01-03 05:15:00 KST\n"
        "End time: 2026-01-03 05:16:00 KST\n"
        "Message: Successfully done!"
    )
    assert payload["blocks"][0]["text"]["text"] == payload["text"]


def test_failure_message_includes_issue_in_english():
    issue = "Database connection failed. Check daily_risk_failed logs for details."
    payload = status_payload(**TIMES, issue=issue)
    assert payload["severity"] == "error"
    assert payload["text"].startswith("Status: Fail\nTitle: Daily Risk Count\n")
    assert payload["text"].endswith("Message: " + issue)
