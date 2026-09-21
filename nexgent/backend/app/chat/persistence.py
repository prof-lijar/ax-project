"""Product chat records. Agent Server checkpoints are not the history database."""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.identity.models import Base, new_id, now


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_chat_owner_activity", "deployment", "owner_id", "updated_at", "id"),
        {"schema": "chat"},
    )
    deployment: Mapped[str] = mapped_column(String(200))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("auth.users.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_chat_message_order", "conversation_id", "position", unique=True),
        {"schema": "chat"},
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("chat.conversations.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="complete")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index(
            "ix_chat_submission", "deployment", "owner_id", "request_key", unique=True
        ),
        Index(
            "ix_chat_active_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_chat_queue", "deployment", "status", "created_at"),
        {"schema": "chat"},
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deployment: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("auth.users.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("chat.conversations.id", ondelete="CASCADE")
    )
    user_message_id: Mapped[str] = mapped_column(
        ForeignKey("chat.messages.id", ondelete="CASCADE")
    )
    assistant_message_id: Mapped[str] = mapped_column(
        ForeignKey("chat.messages.id", ondelete="CASCADE")
    )
    request_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_chat_attachment_order", "conversation_id", "id"),
        {"schema": "chat"},
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("chat.conversations.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    normalized: Mapped[dict] = mapped_column(JSON)


class MessageAttachment(Base):
    __tablename__ = "message_attachments"
    __table_args__: ClassVar = {"schema": "chat"}
    message_id: Mapped[str] = mapped_column(
        ForeignKey("chat.messages.id", ondelete="CASCADE"), primary_key=True
    )
    attachment_id: Mapped[str] = mapped_column(
        ForeignKey("chat.attachments.id", ondelete="CASCADE"), primary_key=True
    )
