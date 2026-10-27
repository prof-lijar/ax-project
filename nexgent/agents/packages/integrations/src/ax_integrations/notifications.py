"""Authenticated submission to the backend's durable notification queue."""

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import httpx
from dotenv import dotenv_values
from pydantic import TypeAdapter


@dataclass(frozen=True)
class BackendNotificationSettings:
    enabled: bool = False
    base_url: str = "http://backend:8000"
    token: str = field(default="", repr=False)
    destination: str = "default"

    @classmethod
    def from_file(
        cls,
        path: Path,
        *,
        base_url: str = "http://backend:8000",
        destination: str = "default",
    ):
        """Use only the backend's mounted settings, including for cron jobs."""
        values = dotenv_values(path, interpolate=False)
        try:
            enabled = TypeAdapter(bool).validate_python(
                values.get("NEXGENT_SLACK_ENABLED") or "false"
            )
            if not enabled:
                return cls()
            token = values.get("NEXGENT_NOTIFICATION_SERVICE_TOKEN") or ""
            channels = json.loads(values.get("NEXGENT_SLACK_CHANNELS") or "{}")
            if (
                not re.fullmatch(r"[\x21-\x7e]{32,512}", token)
                or not isinstance(channels, dict)
                or not isinstance(channels.get(destination), str)
                or not re.fullmatch(r"[CG][A-Z0-9]{8,31}", channels[destination])
            ):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("invalid production notification configuration") from None
        return cls(
            enabled=True, base_url=base_url, token=token, destination=destination
        )


class NotificationError(RuntimeError):
    """Safe error without credentials or upstream response bodies."""


async def submit_notification(
    client, *, base_url, token, key, payload, sleep=asyncio.sleep
):
    """Retry ambiguous submissions with the same immutable body and request key."""
    for attempt in range(3):
        try:
            async with asyncio.timeout(15):
                response = await client.post(
                    base_url.rstrip("/") + "/api/notifications/slack",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Idempotency-Key": key,
                    },
                    json=payload,
                    timeout=15,
                    follow_redirects=False,
                )
        except (TimeoutError, httpx.TimeoutException, httpx.TransportError):
            response = None
        if response is not None:
            if response.status_code == 202:
                try:
                    body = response.json()
                    notification_id = str(UUID(body["id"]))
                    status = body["status"]
                    if status not in {"queued", "sending", "sent", "failed"}:
                        raise ValueError
                    if body["destination"] != payload["destination"]:
                        raise ValueError
                except (ValueError, KeyError, TypeError):
                    raise NotificationError("invalid notification response") from None
                if status == "failed":
                    raise NotificationError("backend notification delivery failed")
                return {"id": notification_id, "status": status}
            if (
                response.status_code not in {408, 425, 429}
                and response.status_code < 500
            ):
                raise NotificationError("notification submission rejected")
        if attempt < 2:
            await sleep(2**attempt)
    raise NotificationError("notification service unavailable")
