"""Authenticated submission to the backend's durable notification queue."""

import asyncio
from uuid import UUID

import httpx


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
                    headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
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
