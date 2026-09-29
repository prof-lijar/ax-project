from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.identity.models import now
from app.identity.store import AccessError
from app.notifications.persistence import Notification, RateGate


def status_view(row):
    result = {name: getattr(row, name) for name in (
        "id", "destination", "status", "attempts", "created_at", "updated_at",
        "sent_at", "error_code", "slack_ts",
    )}
    # PostgreSQL can return the session timezone; SQLite drops timezone metadata.
    for key, value in result.items():
        if isinstance(value, datetime):
            result[key] = (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    return result


class NotificationStore:
    def __init__(self, engine, deployment):
        self.engine = engine
        self.deployment = deployment
        self.sessions = sessionmaker(engine, expire_on_commit=False)

    def ready(self):
        with self.sessions() as db:
            db.execute(select(Notification.id).limit(1))
            db.execute(select(RateGate.key).limit(1))

    def existing(self, owner, key, fingerprint):
        with self.sessions() as db:
            row = db.scalar(select(Notification).where(
                Notification.deployment == self.deployment,
                Notification.owner == owner, Notification.request_key == key,
            ))
            if row is None:
                return None
            if row.fingerprint != fingerprint:
                raise AccessError(409, "idempotency_conflict")
            return status_view(row)

    def enqueue(self, owner, key, fingerprint, destination, channel, payload):
        try:
            with self.sessions.begin() as db:
                insert = pg_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
                for gate in ("workspace", channel):
                    db.execute(insert(RateGate).values(
                        deployment=self.deployment, key=gate, available_at=now(),
                    ).on_conflict_do_nothing())
                row = Notification(
                    deployment=self.deployment, owner=owner, request_key=key,
                    fingerprint=fingerprint, destination=destination,
                    channel_id=channel, payload=payload,
                )
                db.add(row)
                db.flush()
                result = status_view(row)
            return result
        except IntegrityError:
            result = self.existing(owner, key, fingerprint)
            if result is None:
                raise
            return result

    def get(self, owner, ident):
        with self.sessions() as db:
            row = db.scalar(select(Notification).where(
                Notification.id == ident, Notification.owner == owner,
                Notification.deployment == self.deployment,
            ))
            if row is None:
                raise AccessError(404, "notification_not_found")
            return status_view(row)

    def claim(self, settings):
        stamp = now()
        with self.sessions.begin() as db:
            # All workers take locks in workspace -> job order. No DB lock is
            # held while calling Slack. SKIP LOCKED keeps replicas responsive.
            workspace = db.scalar(select(RateGate).where(
                RateGate.deployment == self.deployment, RateGate.key == "workspace",
                RateGate.available_at <= stamp,
            ).with_for_update(skip_locked=True))
            if workspace is None:
                return None
            blocked_channel = exists().where(
                RateGate.deployment == self.deployment,
                RateGate.key == Notification.channel_id,
                RateGate.available_at > stamp,
            )
            row = db.scalar(select(Notification).where(
                Notification.deployment == self.deployment,
                or_(and_(Notification.status == "queued", Notification.available_at <= stamp),
                    and_(Notification.status == "sending", Notification.lease_until <= stamp)),
                ~blocked_channel,
            ).order_by(Notification.available_at, Notification.id).limit(1).with_for_update(skip_locked=True))
            if row is None:
                return None
            if row.attempts >= settings.max_attempts:
                row.status, row.error_code, row.updated_at = "failed", "delivery_attempts_exhausted", stamp
                row.lease_token = row.lease_until = None
                return None
            row.status = "sending"
            row.attempts += 1
            row.updated_at = stamp
            row.lease_token = str(uuid4())
            row.lease_until = stamp + timedelta(seconds=settings.lease_seconds)
            db.execute(update(RateGate).where(
                RateGate.deployment == self.deployment, RateGate.key == row.channel_id,
            ).values(available_at=row.lease_until))
            return {"id": row.id, "token": row.lease_token, "channel_id": row.channel_id,
                    "destination": row.destination, "payload": row.payload, "attempts": row.attempts}

    def finish(self, job, *, slack_ts=None, error_code=None, retry_seconds=None, cooldown_seconds=None):
        stamp = now()
        with self.sessions.begin() as db:
            db.scalar(select(RateGate).where(
                RateGate.deployment == self.deployment, RateGate.key == "workspace",
            ).with_for_update())
            row = db.scalar(select(Notification).where(
                Notification.id == job["id"], Notification.deployment == self.deployment,
                Notification.status == "sending", Notification.lease_token == job["token"],
            ).with_for_update())
            if row is None:
                return False  # A recovered job owns a new lease; stale workers cannot overwrite it.
            if cooldown_seconds is not None:
                # Slack's cooldown applies to this method across the workspace.
                pause = stamp + timedelta(seconds=cooldown_seconds)
                db.execute(update(RateGate).where(
                    RateGate.deployment == self.deployment, RateGate.key == "workspace",
                    RateGate.available_at < pause,
                ).values(available_at=pause))
            db.execute(update(RateGate).where(
                RateGate.deployment == self.deployment, RateGate.key == row.channel_id,
            ).values(available_at=stamp + timedelta(seconds=1)))
            row.updated_at, row.error_code = stamp, error_code
            row.lease_token = row.lease_until = None
            if slack_ts is not None:
                row.status, row.slack_ts, row.sent_at = "sent", slack_ts, stamp
            elif retry_seconds is not None:
                row.status = "queued"
                row.available_at = stamp + timedelta(seconds=retry_seconds)
            else:
                row.status = "failed"
            return True
