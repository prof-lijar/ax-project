from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.identity.models import Base, new_id, now


class Notification(Base):
    __tablename__ = "notification_jobs"
    __table_args__ = (
        Index("ix_notification_idempotency", "deployment", "owner", "request_key", unique=True),
        Index("ix_notification_queue", "deployment", "status", "available_at"),
        {"schema": "notifications"},
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deployment: Mapped[str] = mapped_column(String(200))
    owner: Mapped[str] = mapped_column(String(100))
    request_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    destination: Mapped[str] = mapped_column(String(64))
    channel_id: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    slack_ts: Mapped[str | None] = mapped_column(String(32))


class RateGate(Base):
    __tablename__ = "notification_rate_gates"
    __table_args__ = ({"schema": "notifications"},)
    deployment: Mapped[str] = mapped_column(String(200), primary_key=True)
    # "workspace" coordinates claims and workspace-wide Retry-After pauses.
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
