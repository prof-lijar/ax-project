"""Slack reads and request authentication; no workflow policy or token-bearing logs."""

import hashlib
import hmac
import json
import re
import time
from urllib.parse import urlsplit

import httpx
from slack_sdk.web.async_client import AsyncWebClient

from .file_http import FileIntegrationError, bounded_response
from .slack import (
    CHANNEL_ID_PATTERN,
    SlackMessage,
    SlackMessageResult,
    SlackService,
    SlackSettings,
)


def verify_slack_signature(
    body: bytes, timestamp: str, signature: str, secret: str
) -> bool:
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except ValueError:
        return False
    expected = (
        "v0="
        + hmac.new(
            secret.encode(), b"v0:" + timestamp.encode() + b":" + body, hashlib.sha256
        ).hexdigest()
    )
    return hmac.compare_digest(expected.encode(), signature.encode())


class SlackFiles:
    def __init__(self, token: str, http: httpx.AsyncClient):
        self._token = token
        self.http = http

    async def info(self, method: str, **params) -> dict:
        if method not in {"auth.test", "files.info", "conversations.info"}:
            raise FileIntegrationError("unsupported_slack_method")
        async with self.http.stream(
            "POST" if method == "auth.test" else "GET",
            f"https://slack.com/api/{method}",
            params=params,
            headers={"Authorization": f"Bearer {self._token}"},
        ) as response:
            if response.status_code != 200:
                raise FileIntegrationError("slack_request_failed")
            result = json.loads(await bounded_response(response, 2 * 1024 * 1024))
        if not isinstance(result, dict) or not result.get("ok"):
            raise FileIntegrationError("slack_api_failed")
        return result

    async def identity(self) -> dict[str, str]:
        result = await self.info("auth.test")
        patterns = {
            "team_id": r"T[A-Z0-9]+",
            "user_id": r"[UW][A-Z0-9]+",
            "bot_id": r"B[A-Z0-9]+",
        }
        if any(
            not isinstance(result.get(key), str)
            or not re.fullmatch(pattern, result[key])
            for key, pattern in patterns.items()
        ):
            raise FileIntegrationError("invalid_slack_bot_identity")
        return {key: result[key] for key in patterns}

    async def member_channel(self, channel_id: str) -> dict:
        if not CHANNEL_ID_PATTERN.fullmatch(channel_id):
            raise FileIntegrationError("channel_not_authorized")
        channel = (await self.info("conversations.info", channel=channel_id)).get(
            "channel"
        )
        if (
            not isinstance(channel, dict)
            or channel.get("id") != channel_id
            or channel.get("is_member") is not True
            or channel.get("is_im")
            or channel.get("is_mpim")
        ):
            raise FileIntegrationError("bot_not_channel_member")
        return channel

    async def download(self, url: str, limit: int) -> bytes:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "files.slack.com"
            or parsed.port not in {None, 443}
            or parsed.username
            or parsed.password
        ):
            raise FileIntegrationError("unsafe_slack_download")
        # Never forward a bot token to a redirect destination.
        async with self.http.stream(
            "GET",
            url,
            headers={"Authorization": f"Bearer {self._token}"},
            follow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise FileIntegrationError("slack_download_failed")
            return await bounded_response(response, limit)


class MemberSlackService:
    """Reply only after a fresh membership check; retain SlackService's validation/retries."""

    def __init__(self, token: str, slack: SlackFiles, *, client=None):
        self._token = token
        self._slack = slack
        self._client = client or AsyncWebClient(token=token, timeout=10)

    async def send_message(self, message: SlackMessage) -> SlackMessageResult:
        if message.channel_id is None:
            raise FileIntegrationError("channel_not_authorized")
        await self._slack.member_channel(message.channel_id)
        scoped = SlackService(
            SlackSettings(bot_token=self._token, default_channel_id=message.channel_id),
            client=self._client,
        )
        return await scoped.send_message(message)
