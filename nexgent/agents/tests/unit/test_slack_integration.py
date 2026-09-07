import asyncio
import logging
from typing import Any

import pytest
from ax_integrations import (
    SlackConfigurationError,
    SlackMessage,
    SlackService,
    SlackSettings,
)
from slack_sdk.errors import SlackApiError, SlackRequestError

DEFAULT_CHANNEL = "C0123456789"
REPORTS_CHANNEL = "C0234567890"


class FakeSlackResponse(dict[str, Any]):
    def __init__(
        self,
        payload: dict[str, Any],
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(payload)
        self.status_code = status_code
        self.headers = headers or {}


class FakeSlackClient:
    def __init__(self, responses: list[Any] | None = None) -> None:
        self.responses = responses or [
            {"ok": True, "channel": DEFAULT_CHANNEL, "ts": "123.456"}
        ]
        self.calls: list[dict[str, Any]] = []

    async def chat_postMessage(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def settings(**overrides: Any) -> SlackSettings:
    values: dict[str, Any] = {
        "bot_token": "xoxb-test-token",
        "default_channel_id": DEFAULT_CHANNEL,
        "destinations": {"reports": REPORTS_CHANNEL},
        "request_timeout_seconds": 1,
    }
    values.update(overrides)
    return SlackSettings(**values)


@pytest.mark.asyncio
async def test_successful_delivery_uses_default_channel() -> None:
    client = FakeSlackClient()
    service = SlackService(settings(), client=client)

    result = await service.send_message(SlackMessage(text="hello"))

    assert result.success is True
    assert result.channel_id == DEFAULT_CHANNEL
    assert result.message_ts == "123.456"
    assert client.calls == [{"channel": DEFAULT_CHANNEL, "text": "hello"}]


@pytest.mark.asyncio
async def test_explicit_approved_channel_selection() -> None:
    client = FakeSlackClient(
        [{"ok": True, "channel": REPORTS_CHANNEL, "ts": "234.567"}]
    )
    service = SlackService(settings(), client=client)

    result = await service.send_message(
        SlackMessage(channel_id=REPORTS_CHANNEL, text="report ready")
    )

    assert result.success is True
    assert client.calls[0]["channel"] == REPORTS_CHANNEL


@pytest.mark.asyncio
async def test_default_logical_destination_selects_required_default_channel() -> None:
    client = FakeSlackClient()
    service = SlackService(settings(), client=client)

    result = await service.send_to(destination="default", text="hello")

    assert result.success is True
    assert client.calls[0]["channel"] == DEFAULT_CHANNEL


@pytest.mark.asyncio
async def test_thread_reply_and_blocks_are_forwarded() -> None:
    client = FakeSlackClient()
    service = SlackService(settings(), client=client)
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "hello"}}]

    result = await service.send_message(
        SlackMessage(
            text="accessible fallback",
            thread_ts="123.456",
            blocks=blocks,
        )
    )

    assert result.success is True
    assert client.calls[0]["thread_ts"] == "123.456"
    assert client.calls[0]["blocks"] == blocks


def test_missing_token_is_rejected_without_secret_output() -> None:
    with pytest.raises(SlackConfigurationError, match="SLACK_BOT_TOKEN is required"):
        SlackSettings.from_env({"SLACK_DEFAULT_CHANNEL_ID": DEFAULT_CHANNEL})


def test_missing_default_destination_is_rejected_from_environment() -> None:
    with pytest.raises(
        SlackConfigurationError, match="SLACK_DEFAULT_CHANNEL_ID is required"
    ):
        SlackSettings.from_env({"SLACK_BOT_TOKEN": "xoxb-test-token"})


@pytest.mark.asyncio
async def test_missing_message_destination_returns_clear_result() -> None:
    client = FakeSlackClient()
    service = SlackService(
        settings(default_channel_id=None, destinations={}), client=client
    )

    result = await service.send_message(SlackMessage(text="hello"))

    assert result.success is False
    assert result.error == "missing_destination"
    assert client.calls == []


@pytest.mark.asyncio
async def test_unapproved_channel_and_logical_destination_are_rejected() -> None:
    client = FakeSlackClient()
    service = SlackService(settings(), client=client)

    direct = await service.send_message(
        SlackMessage(channel_id="C0999999999", text="not approved")
    )
    logical = await service.send_to(destination="unknown", text="not approved")

    assert direct.error == "invalid_destination"
    assert logical.error == "invalid_destination"
    assert client.calls == []


@pytest.mark.asyncio
async def test_slack_api_failure_is_sanitized() -> None:
    error = SlackApiError(
        "provider details must not escape",
        FakeSlackResponse({"ok": False, "error": "not_in_channel"}),
    )
    service = SlackService(settings(), client=FakeSlackClient([error]))

    result = await service.send_message(SlackMessage(text="hello"))

    assert result.success is False
    assert result.error == "slack_api_error:not_in_channel"
    assert "provider details" not in result.error


@pytest.mark.asyncio
async def test_rate_limit_waits_then_retries_once() -> None:
    error = SlackApiError(
        "rate limited",
        FakeSlackResponse(
            {"ok": False, "error": "ratelimited"},
            status_code=429,
            headers={"Retry-After": "2"},
        ),
    )
    client = FakeSlackClient(
        [error, {"ok": True, "channel": DEFAULT_CHANNEL, "ts": "345.678"}]
    )
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    service = SlackService(settings(), client=client, sleep=fake_sleep)
    result = await service.send_message(SlackMessage(text="hello"))

    assert result.success is True
    assert waits == [2]
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_timeout_returns_safe_failure() -> None:
    class SlowClient:
        async def chat_postMessage(self, **kwargs: Any) -> Any:
            await asyncio.Event().wait()

    service = SlackService(
        settings(request_timeout_seconds=0.01),
        client=SlowClient(),
    )

    result = await service.send_message(SlackMessage(text="hello"))

    assert result.success is False
    assert result.error == "timeout"


@pytest.mark.asyncio
async def test_token_and_raw_transport_error_are_never_logged_or_returned(
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = "xoxb-super-secret-value"
    client = FakeSlackClient([SlackRequestError(f"failure included {token}")])
    service = SlackService(settings(bot_token=token), client=client)

    with caplog.at_level(logging.WARNING):
        result = await service.send_message(SlackMessage(text="private report body"))

    combined_logs = " ".join(record.getMessage() for record in caplog.records)
    assert result.error == "slack_transport_error"
    assert token not in repr(service.settings)
    assert token not in combined_logs
    assert "private report body" not in combined_logs
    assert "failure included" not in combined_logs
