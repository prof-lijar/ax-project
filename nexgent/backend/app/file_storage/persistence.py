from datetime import datetime

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKey,
                        ForeignKeyConstraint, Index, String, UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column

from app.identity.models import Base, new_id, now


class Blob(Base):
    __tablename__ = "storage_blobs"
    __table_args__ = (
        UniqueConstraint("deployment", "owner_id", "id", name="uq_storage_blob_owner"),
        CheckConstraint("state IN ('uploading', 'ready', 'pending_delete')", name="ck_storage_blob_state"),
        CheckConstraint("size >= 0", name="ck_storage_blob_size"),
        Index("ix_storage_blob_cleanup", "deployment", "state", "created_at"),
        {"schema": "file_storage"},
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deployment: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[str] = mapped_column(ForeignKey("auth.users.id", ondelete="RESTRICT"))
    size: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(String(20), default="uploading")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Entry(Base):
    __tablename__ = "storage_entries"
    __table_args__ = (
        UniqueConstraint("deployment", "owner_id", "id", name="uq_storage_entry_owner"),
        ForeignKeyConstraint(
            ["deployment", "owner_id", "parent_id"],
            ["file_storage.storage_entries.deployment", "file_storage.storage_entries.owner_id", "file_storage.storage_entries.id"],
            name="fk_storage_parent", deferrable=True, initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["deployment", "owner_id", "blob_id"],
            ["file_storage.storage_blobs.deployment", "file_storage.storage_blobs.owner_id", "file_storage.storage_blobs.id"],
            name="fk_storage_blob",
        ),
        CheckConstraint("(kind = 'folder' AND blob_id IS NULL AND size = 0) OR "
                        "(kind = 'file' AND blob_id IS NOT NULL AND size >= 0)", name="ck_storage_entry_kind"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_storage_parent_self"),
        CheckConstraint("(deleted_at IS NULL AND trash_root_id IS NULL) OR "
                        "(deleted_at IS NOT NULL AND trash_root_id IS NOT NULL)", name="ck_storage_trash"),
        Index("uq_storage_root_name", "deployment", "owner_id", "name", unique=True,
              postgresql_where=text("parent_id IS NULL AND deleted_at IS NULL"),
              sqlite_where=text("parent_id IS NULL AND deleted_at IS NULL")),
        Index("uq_storage_child_name", "deployment", "owner_id", "parent_id", "name", unique=True,
              postgresql_where=text("parent_id IS NOT NULL AND deleted_at IS NULL"),
              sqlite_where=text("parent_id IS NOT NULL AND deleted_at IS NULL")),
        Index("ix_storage_entries_owner", "deployment", "owner_id", "parent_id"),
        {"schema": "file_storage"},
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deployment: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[str] = mapped_column(ForeignKey("auth.users.id", ondelete="RESTRICT"))
    parent_id: Mapped[str | None] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(10))
    blob_id: Mapped[str | None] = mapped_column(String(36))
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    content_type: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trash_root_id: Mapped[str | None] = mapped_column(String(36))
