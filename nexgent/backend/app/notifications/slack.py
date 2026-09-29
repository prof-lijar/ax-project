import asyncio
from copy import deepcopy
import math
import re

import httpx


class DeliveryError(Exception):
    def __init__(self, code, *, retryable=False, retry_after=None, rate_limited=False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after
        self.rate_limited = rate_limited


def render_message(job):
    """Plain-text blocks prevent accidental mentions from arbitrary agent output."""
    data = job["payload"]
    if data.get("blocks"):
        return render_native_message(job)
    severity = data["severity"].upper()
    if data.get("locale") == "ko":
        severity = {"info": "안내", "success": "완료", "warning": "확인 필요", "error": "오류"}[data["severity"]]
    title = data.get("title")
    blocks = []
    if title:
        blocks.append({"type": "header", "text": {"type": "plain_text", "text": title}})
    blocks.append({"type": "context", "elements": [{"type": "plain_text", "text": severity}]})
    message = data["text"]
    for offset in range(0, len(message), 3000):
        blocks.append({"type": "section", "text": {"type": "plain_text", "text": message[offset:offset + 3000]}})
    if data.get("fields"):
        blocks.append({"type": "section", "fields": [
            {"type": "plain_text", "text": f"{field['name']}\n{field['value']}"} for field in data["fields"]
        ]})
    table = data.get("table")
    if table:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "table",
            "column_settings": [
                {"align": alignment, "is_wrapped": True}
                for alignment in (table.get("align") or ["left"] * len(table["columns"]))
            ],
            "rows": [
                [{"type": "raw_text", "text": cell} for cell in row]
                for row in [table["columns"], *table["rows"]]
            ],
        })
    if data.get("footer"):
        blocks.append({"type": "divider"})
        blocks.append({"type": "section", "text": {"type": "plain_text", "text": data["footer"]}})
    if data.get("url"):
        blocks.append({"type": "actions", "elements": [{
            "type": "button", "action_id": "notification_open_link",
            "text": {"type": "plain_text", "text": "Open details"}, "url": data["url"],
        }]})
    # Slack still requires a text fallback for notifications and screen readers.
    fallback = f"[{severity}] " + (f"{title}\n" if title else "") + message
    fallback += "".join(f"\n{field['name']}: {field['value']}" for field in data.get("fields", []))
    if table:
        fallback += "\n" + " | ".join(table["columns"])
        fallback += "".join("\n" + " | ".join(row) for row in table["rows"])
    if data.get("footer"):
        fallback += "\n" + data["footer"]
    if data.get("url"):
        fallback += "\n" + data["url"]
    fallback = fallback.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return {
        "channel": job["channel_id"], "text": fallback[:39000], "blocks": blocks,
        "mrkdwn": False, "parse": "none", "unfurl_links": False, "unfurl_media": False,
        "client_msg_id": job["id"],
        **({"thread_ts": data["thread_ts"]} if data.get("thread_ts") else {}),
    }


def render_native_message(job):
    """Render validated Block Kit without adding or discarding caller sections."""
    data = job["payload"]
    def prepare(value):
        if isinstance(value, list):
            return [prepare(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: prepare(item) for key, item in value.items()
                  if item is not None and item != []}
        if result.get("type") == "mrkdwn":
            result["text"] = (result["text"].replace("&", "&amp;")
                              .replace("<", "&lt;").replace(">", "&gt;"))
            result["verbatim"] = True
        return result

    lines = [data["text"]]
    for block in data["blocks"]:
        if block.get("text"):
            lines.append(block["text"]["text"])
        for text in block.get("fields", []) + block.get("elements", []):
            lines.append(text["text"])
        for row in block.get("rows", []):
            lines.append(" | ".join(cell["text"] for cell in row))
    fallback = "\n".join(lines).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return {
        "channel": job["channel_id"], "text": fallback,
        "blocks": prepare(deepcopy(data["blocks"])),
        "mrkdwn": False, "parse": "none", "unfurl_links": False, "unfurl_media": False,
        "client_msg_id": job["id"],
        **({"thread_ts": data["thread_ts"]} if data.get("thread_ts") else {}),
    }


def retry_after(response):
    try:
        value = float(response.headers.get("Retry-After", "60"))
        return value if math.isfinite(value) and 0 < value <= 86400 else 60
    except ValueError:
        return 60


class SlackClient:
    def __init__(self, client: httpx.AsyncClient, settings):
        self.client = client
        self.settings = settings

    async def send(self, job):
        try:
            # A total deadline bounds the lease even if a peer trickles bytes.
            async with asyncio.timeout(self.settings.timeout_seconds):
                response = await self.client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {self.settings.bot_token.get_secret_value()}"},
                    json=render_message(job), timeout=self.settings.timeout_seconds,
                )
        except (httpx.TransportError, TimeoutError):
            raise DeliveryError("slack_transport_error", retryable=True) from None
        if response.status_code == 429:
            raise DeliveryError("slack_rate_limited", retryable=True,
                                retry_after=retry_after(response), rate_limited=True)
        if response.status_code >= 500 or response.status_code == 408:
            raise DeliveryError("slack_unavailable", retryable=True)
        if response.status_code != 200:
            raise DeliveryError("slack_http_error")
        try:
            data = response.json()
        except ValueError:
            raise DeliveryError("slack_invalid_response", retryable=True) from None
        if not isinstance(data, dict):
            raise DeliveryError("slack_invalid_response", retryable=True)
        if data.get("ok") is not True:
            code = data.get("error")
            if code in ("ratelimited", "rate_limited"):
                raise DeliveryError("slack_rate_limited", retryable=True,
                                    retry_after=retry_after(response), rate_limited=True)
            # Only known codes leave this boundary; never persist arbitrary upstream text.
            if code in ("internal_error", "service_unavailable", "fatal_error"):
                raise DeliveryError("slack_unavailable", retryable=True)
            if code in ("invalid_auth", "token_revoked", "account_inactive", "missing_scope", "not_authed"):
                raise DeliveryError("slack_authentication_failed")
            if code in ("channel_not_found", "not_in_channel", "is_archived"):
                raise DeliveryError("slack_destination_unavailable")
            raise DeliveryError("slack_rejected")
        ts = data.get("ts")
        if not isinstance(ts, str) or not re.fullmatch(r"\d{10,}\.[0-9]{6}", ts) or len(ts) > 32:
            raise DeliveryError("slack_invalid_response", retryable=True)
        return ts
