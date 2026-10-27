"""Best-effort submission through the backend's durable Slack queue."""

import os
from pathlib import Path
from uuid import uuid4

import httpx
from ax_integrations.notifications import (
    BackendNotificationSettings,
    submit_notification,
)

from workflows.daily_risk_counts.notification import status_payload

PRODUCTION_NOTIFICATION_ENV = Path("/run/ax-notifications/prod.env")


async def notify_status(day, *, started_at, ended_at, issue=None, event):
    """Slack failure never changes the database outcome or triggers a DB retry."""
    try:
        settings = BackendNotificationSettings.from_file(
            PRODUCTION_NOTIFICATION_ENV,
            destination="daily_risk",
            # This scheduler uses host networking for its local database.
            base_url=os.environ.get(
                "DAILY_RISK_NOTIFICATION_BASE_URL", "http://127.0.0.1:8001"
            ),
        )
        if not settings.enabled:
            event("daily_risk_notification_disabled", date=day.isoformat())
            return
        # Each invocation reports its own result. Transport retries reuse this
        # exact key and payload; manual reconciliation is a distinct invocation.
        key = f"daily-risk:{day.isoformat()}:{uuid4()}"
        async with httpx.AsyncClient(trust_env=False) as client:
            accepted = await submit_notification(
                client,
                base_url=settings.base_url,
                token=settings.token,
                key=key,
                payload=status_payload(
                    started_at=started_at, ended_at=ended_at, issue=issue
                ),
            )
        event("daily_risk_notification_accepted", date=day.isoformat(), **accepted)
    except Exception as exc:  # noqa: BLE001 -- preserve the DB result; omit secrets
        event(
            "daily_risk_notification_failed",
            date=day.isoformat(),
            error_type=type(exc).__name__,
        )
