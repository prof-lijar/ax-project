"""Reusable, outbound-only Slack Web API integration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

import aiohttp
from slack_sdk.errors import SlackApiError, SlackClientError
from slack_sdk.web.async_client import AsyncWebClient

CHANNEL_ID_PATTERN = re.compile(r"^[CG][A-Z0-9]{8,}$")
DESTINATION_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
THREAD_TS_PATTERN = re.compile(r"^[0-9]{1,16}\.[0-9]{1,16}$")
ERROR_CODE_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")
MAX_TEXT_CHARACTERS = 40_000
MAX_BLOCKS = 50
MAX_BLOCKS_JSON_BYTES = 100_000

logger = logging.getLogger(__name__)


class SlackConfigurationError(ValueError):
    """Safe Slack configuration failure that never contains token values."""


@dataclass(frozen=True, slots=True)
class SlackMessage:
    text: str
    channel_id: str | None = None
    thread_ts: str | None = None
    blocks: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SlackMessageResult:
    success: bool
    channel_id: str | None = None
    message_ts: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class SlackSettings:
    bot_token: str = field(repr=False)
    default_channel_id: str | None = None
    destinations: Mapping[str, str] = field(default_factory=dict)
    request_timeout_seconds: float = 10.0
    rate_limit_max_retries: int = 1
    rate_limit_max_wait_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.bot_token:
            raise SlackConfigurationError("SLACK_BOT_TOKEN must not be empty")
        if not self.bot_token.startswith("xoxb-"):
            raise SlackConfigurationError("SLACK_BOT_TOKEN must be a bot token")
        if self.default_channel_id is not None:
            _require_channel_id(self.default_channel_id, "SLACK_DEFAULT_CHANNEL_ID")
        normalized: dict[str, str] = {}
        for name, channel_id in self.destinations.items():
            normalized_name = name.strip().lower()
            if not DESTINATION_PATTERN.fullmatch(normalized_name):
                raise SlackConfigurationError("Slack destination name is invalid")
            _require_channel_id(channel_id, f"Slack destination {normalized_name}")
            normalized[normalized_name] = channel_id
        object.__setattr__(self, "destinations", MappingProxyType(normalized))
        if not 0 < self.request_timeout_seconds <= 120:
            raise SlackConfigurationError("Slack request timeout must be between 0 and 120")
        if not 0 <= self.rate_limit_max_retries <= 3:
            raise SlackConfigurationError("Slack rate-limit retries must be between 0 and 3")
        if not 0 <= self.rate_limit_max_wait_seconds <= 120:
            raise SlackConfigurationError("Slack rate-limit wait must be between 0 and 120")

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> SlackSettings:
        values = os.environ if environ is None else environ
        token = values.get("SLACK_BOT_TOKEN", "")
        default_channel = values.get("SLACK_DEFAULT_CHANNEL_ID", "")
        if not token:
            raise SlackConfigurationError("SLACK_BOT_TOKEN is required")
        if not default_channel:
            raise SlackConfigurationError("SLACK_DEFAULT_CHANNEL_ID is required")
        destinations = {
            key.removeprefix("SLACK_CHANNEL_").lower(): value
            for key, value in values.items()
            if key.startswith("SLACK_CHANNEL_") and value
        }
        try:
            timeout = float(values.get("SLACK_REQUEST_TIMEOUT_SECONDS", "10"))
        except ValueError as exc:
            raise SlackConfigurationError(
                "SLACK_REQUEST_TIMEOUT_SECONDS must be numeric"
            ) from exc
        return cls(
            bot_token=token,
            default_channel_id=default_channel,
            destinations=destinations,
            request_timeout_seconds=timeout,
        )

    @property
    def approved_channel_ids(self) -> frozenset[str]:
        channel_ids = set(self.destinations.values())
        if self.default_channel_id is not None:
            channel_ids.add(self.default_channel_id)
        return frozenset(channel_ids)


class SlackWebClient(Protocol):
    def chat_postMessage(self, **kwargs: Any) -> Awaitable[Any]: ...


Sleep = Callable[[float], Awaitable[None]]


class SlackService:
    """Send validated messages only to application-approved Slack channels."""

    def __init__(
        self,
        settings: SlackSettings,
        *,
        client: SlackWebClient | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.settings = settings
        self._client = client or AsyncWebClient(
            token=settings.bot_token,
            timeout=max(1, int(settings.request_timeout_seconds)),
        )
        self._sleep = sleep

    async def send_message(self, message: SlackMessage) -> SlackMessageResult:
        destination = message.channel_id or self.settings.default_channel_id
        error = _validate_message(message, destination, self.settings)
        if error is not None:
            self._log_failure(destination, error)
            return SlackMessageResult(
                success=False,
                channel_id=destination,
                error=error,
            )

        assert destination is not None
        payload: dict[str, Any] = {
            "channel": destination,
            "text": message.text,
        }
        if message.thread_ts is not None:
            payload["thread_ts"] = message.thread_ts
        if message.blocks is not None:
            payload["blocks"] = message.blocks

        attempts = self.settings.rate_limit_max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                response = await asyncio.wait_for(
                    self._client.chat_postMessage(**payload),
                    timeout=self.settings.request_timeout_seconds,
                )
            except SlackApiError as exc:
                if _is_rate_limited(exc):
                    if attempt < attempts:
                        wait_seconds = _retry_after_seconds(exc)
                        if wait_seconds <= self.settings.rate_limit_max_wait_seconds:
                            logger.warning(
                                "slack_delivery_rate_limited",
                                extra={
                                    "slack_event": "delivery_rate_limited",
                                    "slack_channel_id": destination,
                                    "slack_retry_attempt": attempt,
                                    "slack_retry_after_seconds": wait_seconds,
                                },
                            )
                            await self._sleep(wait_seconds)
                            continue
                    self._log_failure(destination, "rate_limited")
                    return SlackMessageResult(
                        success=False,
                        channel_id=destination,
                        error="rate_limited",
                    )
                error_code = f"slack_api_error:{_safe_api_error_code(exc)}"
                self._log_failure(destination, error_code)
                return SlackMessageResult(
                    success=False,
                    channel_id=destination,
                    error=error_code,
                )
            except TimeoutError:
                self._log_failure(destination, "timeout")
                return SlackMessageResult(
                    success=False,
                    channel_id=destination,
                    error="timeout",
                )
            except (SlackClientError, aiohttp.ClientError, OSError) as exc:
                self._log_failure(
                    destination,
                    "slack_transport_error",
                    exception_type=type(exc).__name__,
                )
                return SlackMessageResult(
                    success=False,
                    channel_id=destination,
                    error="slack_transport_error",
                )

            if not bool(response.get("ok", False)):
                self._log_failure(destination, "slack_api_error:unknown_error")
                return SlackMessageResult(
                    success=False,
                    channel_id=destination,
                    error="slack_api_error:unknown_error",
                )
            channel_id = response.get("channel")
            message_ts = response.get("ts")
            safe_channel_id = channel_id if isinstance(channel_id, str) else destination
            safe_message_ts = message_ts if isinstance(message_ts, str) else None
            logger.info(
                "slack_delivery_succeeded",
                extra={
                    "slack_event": "delivery_succeeded",
                    "slack_channel_id": safe_channel_id,
                    "slack_message_ts": safe_message_ts,
                    "slack_has_blocks": message.blocks is not None,
                    "slack_is_thread_reply": message.thread_ts is not None,
                },
            )
            return SlackMessageResult(
                success=True,
                channel_id=safe_channel_id,
                message_ts=safe_message_ts,
            )

        raise AssertionError("unreachable Slack retry state")

    async def send_to(
        self,
        *,
        destination: str,
        text: str,
        thread_ts: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SlackMessageResult:
        normalized = destination.strip().lower()
        channel_id = (
            self.settings.default_channel_id
            if normalized == "default"
            else self.settings.destinations.get(normalized)
        )
        if channel_id is None:
            self._log_failure(None, "invalid_destination")
            return SlackMessageResult(success=False, error="invalid_destination")
        return await self.send_message(
            SlackMessage(
                channel_id=channel_id,
                text=text,
                thread_ts=thread_ts,
                blocks=blocks,
                metadata=metadata or {},
            )
        )

    @staticmethod
    def _log_failure(
        channel_id: str | None,
        error_code: str,
        *,
        exception_type: str | None = None,
    ) -> None:
        logger.warning(
            "slack_delivery_failed",
            extra={
                "slack_event": "delivery_failed",
                "slack_channel_id": channel_id,
                "slack_error_code": error_code,
                "slack_exception_type": exception_type,
            },
        )


def _require_channel_id(value: str, label: str) -> None:
    if not CHANNEL_ID_PATTERN.fullmatch(value):
        raise SlackConfigurationError(f"{label} must be a Slack channel ID")


def _validate_message(
    message: SlackMessage,
    destination: str | None,
    settings: SlackSettings,
) -> str | None:
    if destination is None:
        return "missing_destination"
    if not CHANNEL_ID_PATTERN.fullmatch(destination):
        return "invalid_destination"
    if destination not in settings.approved_channel_ids:
        return "invalid_destination"
    if not isinstance(message.text, str) or not message.text.strip():
        return "invalid_message"
    if len(message.text) > MAX_TEXT_CHARACTERS:
        return "invalid_message"
    if message.thread_ts is not None and not THREAD_TS_PATTERN.fullmatch(
        message.thread_ts
    ):
        return "invalid_thread_ts"
    if message.blocks is not None:
        if (
            not isinstance(message.blocks, list)
            or not message.blocks
            or len(message.blocks) > MAX_BLOCKS
            or any(not isinstance(block, dict) for block in message.blocks)
        ):
            return "invalid_blocks"
        try:
            serialized = json.dumps(message.blocks, ensure_ascii=False)
        except (TypeError, ValueError):
            return "invalid_blocks"
        if len(serialized.encode("utf-8")) > MAX_BLOCKS_JSON_BYTES:
            return "invalid_blocks"
    if not isinstance(message.metadata, dict):
        return "invalid_metadata"
    try:
        json.dumps(message.metadata, ensure_ascii=False)
    except (TypeError, ValueError):
        return "invalid_metadata"
    return None


def _is_rate_limited(exc: SlackApiError) -> bool:
    response = exc.response
    return getattr(response, "status_code", None) == 429 or response.get("error") in {
        "rate_limited",
        "ratelimited",
    }


def _retry_after_seconds(exc: SlackApiError) -> float:
    headers = getattr(exc.response, "headers", {}) or {}
    value: object = "1"
    for key, candidate in headers.items():
        if str(key).lower() == "retry-after":
            value = candidate
            break
    if isinstance(value, (list, tuple)):
        value = value[0] if value else "1"
    try:
        return max(0.0, float(str(value)))
    except ValueError:
        return 1.0


def _safe_api_error_code(exc: SlackApiError) -> str:
    candidate = exc.response.get("error")
    if isinstance(candidate, str) and ERROR_CODE_PATTERN.fullmatch(candidate):
        return candidate
    return "unknown_error"


__all__ = [
    "SlackConfigurationError",
    "SlackMessage",
    "SlackMessageResult",
    "SlackService",
    "SlackSettings",
    "SlackWebClient",
]
