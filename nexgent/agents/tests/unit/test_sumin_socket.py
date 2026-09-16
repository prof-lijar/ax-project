import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml
from ax_integrations.slack_socket import SlackSocket, _SafeTransportLog

from apps.sumin.socket import event_handler
from workflows.sumin.settings import Settings


def client():
    return SimpleNamespace(
        socket_mode_request_listeners=[],
        send_socket_mode_response=AsyncMock(),
        connect=AsyncMock(),
        close=AsyncMock(),
        is_connected=AsyncMock(return_value=True),
    )


def request(**overrides):
    return SimpleNamespace(
        type="events_api",
        envelope_id="envelope-1",
        payload={
            "type": "event_callback",
            "team_id": "T12345678",
            "event_id": "Ev123",
            "event": {
                "type": "file_shared",
                "channel_id": "C12345678",
                "file_id": "F12345678",
            },
        },
        **overrides,
    )


@pytest.mark.asyncio
async def test_socket_commits_before_ack_and_replay_reuses_task_identity():
    settings = Settings(
        bot_token="xoxb-test",
        app_token="xapp-test",
        database_dsn="unused",
        nextcloud_url="https://cloud.example",
        nextcloud_user="sumin",
        nextcloud_password="unused",
        team_id="T12345678",
        bot_user_id="U12345678",
    )
    calls = []

    async def enqueue(tasks):
        calls.append(("commit", tasks[0].key))

    sdk = client()

    async def ack(response):
        calls.append(("ack", response.envelope_id))

    sdk.send_socket_mode_response.side_effect = ack
    socket = SlackSocket(
        "xapp-test",
        "xoxb-test",
        event_handler(settings, SimpleNamespace(enqueue=enqueue)),
        client=sdk,
    )
    for _ in range(2):
        await socket.receive(sdk, request())
    assert calls == [("commit", "T12345678:Ev123:F12345678"), ("ack", "envelope-1")] * 2
    assert not socket.active


@pytest.mark.asyncio
async def test_socket_database_failure_is_not_acknowledged_or_logged(caplog):
    sdk = client()
    socket = SlackSocket(
        "xapp-test",
        "xoxb-test",
        AsyncMock(side_effect=OSError("private-data")),
        client=sdk,
    )
    with caplog.at_level(logging.WARNING):
        await socket.receive(sdk, request())
    sdk.send_socket_mode_response.assert_not_awaited()
    assert "private-data" not in caplog.text
    assert not socket.active


@pytest.mark.asyncio
async def test_socket_backpressure_and_cancellation_leave_work_unacknowledged():
    sdk = client()
    handler = AsyncMock(side_effect=asyncio.CancelledError())
    socket = SlackSocket("xapp-test", "xoxb-test", handler, client=sdk)
    socket.active = {object() for _ in range(4)}
    await socket.receive(sdk, request())
    handler.assert_not_awaited()
    socket.active.clear()
    with pytest.raises(asyncio.CancelledError):
        await socket.receive(sdk, request())
    assert not socket.active
    sdk.send_socket_mode_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_socket_oversized_event_does_not_reach_handler():
    sdk = client()
    handler = AsyncMock()
    socket = SlackSocket("xapp-test", "xoxb-test", handler, client=sdk)
    event = request()
    event.payload = {"text": "x" * (1024 * 1024)}
    await socket.receive(sdk, event)
    handler.assert_not_awaited()
    sdk.send_socket_mode_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_socket_connect_and_shutdown_close_transport():
    sdk = client()
    stop = asyncio.Event()
    sdk.connect.side_effect = stop.set
    socket = SlackSocket("xapp-test", "xoxb-test", AsyncMock(), client=sdk)
    await socket.run(stop)
    sdk.connect.assert_awaited_once()
    sdk.close.assert_awaited_once()
    assert socket.closing


@pytest.mark.asyncio
async def test_socket_failed_connect_closes_transport():
    sdk = client()
    sdk.connect.side_effect = TimeoutError()
    socket = SlackSocket("xapp-test", "xoxb-test", AsyncMock(), client=sdk)
    with pytest.raises(TimeoutError):
        await socket.run(asyncio.Event())
    sdk.close.assert_awaited_once()


def test_transport_log_redacts_websocket_secrets():
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        "test",
        1,
        "secret wss://token %s",
        ("app-token",),
        (RuntimeError, RuntimeError("private"), None),
    )
    assert _SafeTransportLog().filter(record)
    assert record.getMessage() == "slack_socket_transport"
    assert record.exc_info is None


def test_compose_socket_mode_and_loopback_database_access():
    services = yaml.safe_load(Path("compose.sumin.yaml").read_text())["services"]
    assert set(services) == {"sumin-migrate", "sumin-events", "sumin-worker"}
    assert services["sumin-events"]["command"][-1] == "apps.sumin.socket"
    assert all(
        service["network_mode"] == "host" and "ports" not in service
        for service in services.values()
    )
    ca = services["sumin-worker"]["volumes"][0]
    assert ca["read_only"] and not ca["bind"]["create_host_path"]
    manifest = json.loads(Path("config/sumin-slack-manifest.json").read_text())
    assert manifest["settings"]["socket_mode_enabled"]
    assert "request_url" not in manifest["settings"]["event_subscriptions"]


def test_wrong_app_token_rejected_without_connection():
    with pytest.raises(ValueError, match="xapp-"):
        SlackSocket("xoxb-wrong", "xoxb-test", AsyncMock(), client=client())
