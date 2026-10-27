"""Resume notification submission independently of committed report migration."""

import asyncio
import json
import os
from pathlib import Path

import httpx
from ax_integrations.notifications import (
    BackendNotificationSettings,
    NotificationError,
    submit_notification,
)

from workflows.weekly_report.completion_notification import notification_payload

PRODUCTION_NOTIFICATION_ENV = Path("/run/ax-notifications/prod.env")


class NotificationSettings(BackendNotificationSettings):
    @classmethod
    def from_env(cls):
        return cls.from_file(PRODUCTION_NOTIFICATION_ENV)


def write_state(path, data):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as output:
        json.dump(data, output, ensure_ascii=False)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def notify_completed_week(week_start, state_root, *, settings, collect, send=None):
    if not settings.enabled:
        return
    pending = state_root / f"{week_start}.notification.json"
    if pending.exists():
        event = json.loads(pending.read_text())
        if event.get("accepted"):
            return event["accepted"]
    else:
        coverage_path = state_root / f"{week_start}.coverage.json"
        # Reuse a completed snapshot after interruption before payload persistence.
        if not coverage_path.exists():
            collect(week_start, coverage_path)
        try:
            payload = notification_payload(
                json.loads(coverage_path.read_text()),
                week_start=week_start,
                destination=settings.destination,
            )
        except (ValueError, KeyError, TypeError):
            raise NotificationError("invalid local coverage snapshot") from None
        event = {
            "key": f"weekly-report:production:{week_start}:coverage-v1",
            "payload": payload,
            "base_url": settings.base_url,
        }
        write_state(pending, event)
    if event["base_url"] != settings.base_url:
        raise NotificationError("notification backend changed during recovery")
    result = send(event) if send else send_event(settings, event)
    event["accepted"] = result
    write_state(pending, event)
    return result


def send_event(settings, event):
    """Submit an immutable completion or failure event through the backend API."""
    if event["base_url"] != settings.base_url:
        raise NotificationError("notification backend changed during recovery")

    async def send_to_backend():
        async with httpx.AsyncClient(trust_env=False) as client:
            return await submit_notification(
                client,
                base_url=settings.base_url,
                token=settings.token,
                key=event["key"],
                payload=event["payload"],
            )

    return asyncio.run(send_to_backend())
