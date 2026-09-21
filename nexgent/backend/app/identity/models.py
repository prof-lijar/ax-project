from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    metadata = MetaData(schema="auth", naming_convention={"ix": "ix_%(table_name)s_%(column_0_name)s"})


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), default="")
    # Imported accounts cannot log in until an admin sets a local password.
    password_hash: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (CheckConstraint("token_version >= 0", name="user_token_version"),)


class Group(Base):
    __tablename__ = "groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(500), default="")


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class UserGroup(Base):
    __tablename__ = "user_groups"
    user_id: Mapped[str] = mapped_column(ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("auth.groups.id", ondelete="CASCADE"), primary_key=True, index=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[str] = mapped_column(ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("auth.roles.id", ondelete="CASCADE"), primary_key=True, index=True)


class GroupRole(Base):
    __tablename__ = "group_roles"
    group_id: Mapped[str] = mapped_column(ForeignKey("auth.groups.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("auth.roles.id", ondelete="CASCADE"), primary_key=True, index=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[str] = mapped_column(ForeignKey("auth.roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[str] = mapped_column(ForeignKey("auth.permissions.id", ondelete="CASCADE"), primary_key=True, index=True)


ADMIN_ROLE_ID = "00000000-0000-0000-0000-000000000001"
ADMIN_PERMISSION_ID = "00000000-0000-0000-0000-000000000002"
