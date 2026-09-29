"""Resume notification submission independently of committed report migration."""

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from ax_integrations.notifications import NotificationError, submit_notification
from dotenv import dotenv_values

from workflows.weekly_report.completion_notification import notification_payload


@dataclass(frozen=True)
class NotificationSettings:
    enabled: bool = False
    base_url: str = "http://backend:8000"
    token: str = field(default="", repr=False)
    destination: str = "default"

    @classmethod
    def from_env(cls):
        values = {
            **dotenv_values(Path(__file__).resolve().parents[2] / ".env"),
            **os.environ,
        }
        enabled = (values.get("WEEKLY_REPORT_NOTIFICATION_ENABLED") or "false").lower()
        if enabled not in {"true", "false"}:
            raise ValueError("invalid notification enabled setting")
        if enabled == "false":
            return cls()
        base = values.get("WEEKLY_REPORT_NOTIFICATION_API_URL") or "http://backend:8000"
        token = values.get("WEEKLY_REPORT_NOTIFICATION_SERVICE_TOKEN") or ""
        destination = values.get("WEEKLY_REPORT_NOTIFICATION_DESTINATION") or "default"
        try:
            parsed = urlsplit(base)
            valid = (
                parsed.scheme in {"http", "https"}
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and not parsed.query
                and not parsed.fragment
            )
            _ = parsed.port
        except ValueError:
            valid = False
        if (
            not valid
            or not re.fullmatch(r"[\x21-\x7e]{32,512}", token)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", destination)
        ):
            raise ValueError("invalid notification configuration")
        return cls(True, base.rstrip("/"), token, destination)


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
            raise NotificationError("invalid production coverage snapshot") from None
        event = {
            "key": f"weekly-report:production:{week_start}:coverage-v1",
            "payload": payload,
            "base_url": settings.base_url,
        }
        write_state(pending, event)
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

    result = send(event) if send else asyncio.run(send_to_backend())
    event["accepted"] = result
    write_state(pending, event)
    return result
