from hashlib import sha256
import json

from pydantic import TypeAdapter

from app.identity.store import AccessError
from app.notifications.schemas import RequestKey, SlackNotification


class NotificationService:
    """Reusable submission boundary for routes and in-process integrations."""

    def __init__(self, store, settings):
        self.store = store
        self.settings = settings

    def submit(self, owner: str, payload: SlackNotification, request_key: str):
        if not self.settings.enabled:
            raise AccessError(503, "notifications_disabled")
        request_key = TypeAdapter(RequestKey).validate_python(request_key)
        data = payload.model_dump(mode="json")
        fingerprint = sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        # Resolve idempotency before channel lookup so configuration changes never
        # reroute a previously accepted request.
        existing = self.store.existing(owner, request_key, fingerprint)
        if existing:
            return existing
        channel = self.settings.channels.get(payload.destination)
        if channel is None:
            raise AccessError(422, "unknown_notification_destination")
        return self.store.enqueue(owner, request_key, fingerprint, payload.destination, channel, data)
