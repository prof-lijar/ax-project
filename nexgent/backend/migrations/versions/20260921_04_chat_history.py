"""Private chat history, durable execution queue and attachment metadata."""

from alembic import op

import sqlalchemy as sa

revision = "20260921_04"
down_revision = "20260917_03"
branch_labels = None
depends_on = None


def upgrade():
    pg = op.get_bind().dialect.name == "postgresql"
    schema = "chat" if pg else None
    prefix = "chat." if pg else ""
    users = "auth.users.id" if pg else "users.id"
    if pg:
        op.execute("CREATE SCHEMA IF NOT EXISTS chat")

    def column(name, type_, **kwargs):
        return sa.Column(name, type_, nullable=False, **kwargs)

    def foreign(name, target, **kwargs):
        return sa.Column(
            name,
            sa.String(36),
            sa.ForeignKey(target, ondelete="CASCADE"),
            nullable=False,
            **kwargs,
        )

    op.create_table(
        "conversations",
        column("deployment", sa.String(200)),
        column("id", sa.String(36), primary_key=True),
        foreign("owner_id", users),
        column("title", sa.String(120)),
        column("created_at", sa.DateTime(timezone=True)),
        column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        schema=schema,
    )
    op.create_index(
        "ix_chat_owner_activity",
        "conversations",
        ["deployment", "owner_id", "updated_at", "id"],
        schema=schema,
    )
    op.create_table(
        "messages",
        column("id", sa.String(36), primary_key=True),
        foreign("conversation_id", prefix + "conversations.id"),
        column("position", sa.Integer()),
        column("role", sa.String(16)),
        column("content", sa.Text()),
        column("status", sa.String(20)),
        column("created_at", sa.DateTime(timezone=True)),
        schema=schema,
    )
    op.create_index(
        "ix_chat_message_order",
        "messages",
        ["conversation_id", "position"],
        unique=True,
        schema=schema,
    )
    op.create_table(
        "runs",
        column("id", sa.String(36), primary_key=True),
        column("deployment", sa.String(200)),
        foreign("owner_id", users),
        foreign("conversation_id", prefix + "conversations.id"),
        foreign("user_message_id", prefix + "messages.id"),
        foreign("assistant_message_id", prefix + "messages.id"),
        column("request_key", sa.String(128)),
        column("fingerprint", sa.String(64)),
        column("status", sa.String(20)),
        column("revision", sa.Integer()),
        column("cancel_requested", sa.Boolean()),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
        column("created_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        schema=schema,
    )
    op.create_index(
        "ix_chat_submission",
        "runs",
        ["deployment", "owner_id", "request_key"],
        unique=True,
        schema=schema,
    )
    op.create_index(
        "ix_chat_active_conversation",
        "runs",
        ["conversation_id"],
        unique=True,
        schema=schema,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index(
        "ix_chat_queue", "runs", ["deployment", "status", "created_at"], schema=schema
    )
    op.create_table(
        "attachments",
        column("id", sa.String(36), primary_key=True),
        foreign("conversation_id", prefix + "conversations.id"),
        column("name", sa.String(255)),
        column("size", sa.Integer()),
        column("media_type", sa.String(100)),
        column("sha256", sa.String(64)),
        column("normalized", sa.JSON()),
        schema=schema,
    )
    op.create_index(
        "ix_chat_attachment_order",
        "attachments",
        ["conversation_id", "id"],
        schema=schema,
    )
    op.create_table(
        "message_attachments",
        foreign("message_id", prefix + "messages.id", primary_key=True),
        foreign("attachment_id", prefix + "attachments.id", primary_key=True),
        schema=schema,
    )


def downgrade():
    schema = "chat" if op.get_bind().dialect.name == "postgresql" else None
    for name in (
        "message_attachments",
        "attachments",
        "runs",
        "messages",
        "conversations",
    ):
        op.drop_table(name, schema=schema)
