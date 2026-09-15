"""Slack reads and request authentication; no workflow policy or token-bearing logs."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlsplit

import httpx

from .file_http import FileIntegrationError, bounded_response


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
        if method not in {"files.info", "conversations.info"}:
            raise FileIntegrationError("unsupported_slack_method")
        async with self.http.stream(
            "GET",
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
