from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Literal

import httpx

from app.models import ScoutRunResponse


def format_slack_report(report: str) -> str:
    """Render Scout's Markdown subset as Slack mrkdwn without enabling mentions."""
    escaped = report.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Keep code and links out of emphasis substitutions (URLs can contain underscores).
    tokens = re.compile(
        r"(```[\s\S]*?```|`[^`\n]+`|"
        r"\[([^\]\n]+)\]\((https?://(?:[^\s()]|\([^\s()]*\))+)\)|"
        r"https?://[^\s<>]+)"
    )

    def prose(text: str) -> str:
        text = re.sub(r"(?m)^ {0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", r"**\1**", text)
        text = re.sub(r"(?m)^([ \t]*)[-*+][ \t]+", r"\1• ", text)
        text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"*{m[1] or m[2]}*", text)
        return text

    lines = []
    cursor = 0
    for match in tokens.finditer(escaped):
        lines.append(prose(escaped[cursor : match.start()]))
        value = match[0]
        if value.startswith("`"):
            lines.append(value)
        elif match[3]:
            url = match[3].replace("|", "%7C")
            label = match[2].replace("|", "¦")
            lines.append(f"<{url}|{label}>")
        else:
            # parse=none disables autolinking; explicitly link bare source URLs.
            url = value.rstrip(".,;:!?)")
            suffix = value[len(url) :]
            lines.append(f"<{url.replace('|', '%7C')}>{suffix}")
        cursor = match.end()
    lines.append(prose(escaped[cursor:]))
    return "".join(lines)


@dataclass(frozen=True, slots=True)
class SlackDelivery:
    status: Literal["sent", "skipped", "failed"]
    reason: str


class SlackNotifier:
    """One bounded delivery attempt; credentials and response bodies never enter logs."""

    def __init__(
        self,
        token: str | None,
        channel_id: str | None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._channel_id = channel_id
        self._transport = transport

    async def send(self, run: ScoutRunResponse) -> SlackDelivery:
        if not self._token and not self._channel_id:
            return SlackDelivery("skipped", "not_configured")
        if not self._token or not self._channel_id:
            return SlackDelivery("failed", "incomplete_configuration")

        text = (
            f"*Scout research completed*\nRun: {run.run_id}\nSources: {run.source_count}\n\n"
            + format_slack_report(run.report)
        )
        if len(text) > 39_000:
            return SlackDelivery("failed", "message_too_long")

        try:
            async with (
                asyncio.timeout(12),
                httpx.AsyncClient(
                    transport=self._transport, timeout=10, follow_redirects=False
                ) as client,
            ):
                response = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {self._token}"},
                    json={
                        "channel": self._channel_id,
                        "text": text,
                        "mrkdwn": True,
                        "parse": "none",
                        "link_names": False,
                        "unfurl_links": False,
                        "unfurl_media": False,
                    },
                )
                if response.status_code == 429:
                    return SlackDelivery("failed", "rate_limited")
                if response.status_code != 200:
                    return SlackDelivery("failed", "http_error")
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("ok") is not True:
                    return SlackDelivery("failed", "api_error")
                return SlackDelivery("sent", "accepted")
        except (TimeoutError, httpx.TimeoutException):
            return SlackDelivery("failed", "timeout")
        except Exception:
            return SlackDelivery("failed", "transport_or_response_error")
