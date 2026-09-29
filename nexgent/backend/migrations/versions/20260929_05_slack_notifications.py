"""Durable notification jobs and shared Slack rate gates."""

from alembic import op
import sqlalchemy as sa

revision = "20260929_05"
down_revision = "20260921_04"
branch_labels = None
depends_on = None


def upgrade():
    schema = "notifications" if op.get_bind().dialect.name == "postgresql" else None
    if schema:
        op.execute("CREATE SCHEMA IF NOT EXISTS notifications")

    def required(name, type_, **kwargs):
        return sa.Column(name, type_, nullable=False, **kwargs)

    op.create_table(
        "notification_jobs",
        required("id", sa.String(36), primary_key=True),
        required("deployment", sa.String(200)),
        required("owner", sa.String(100)),
        required("request_key", sa.String(128)),
        required("fingerprint", sa.String(64)),
        required("destination", sa.String(64)),
        required("channel_id", sa.String(32)),
        required("payload", sa.JSON()),
        required("status", sa.String(16)),
        required("attempts", sa.Integer()),
        required("available_at", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        required("created_at", sa.DateTime(timezone=True)),
        required("updated_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("slack_ts", sa.String(32)),
        schema=schema,
    )
    op.create_index("ix_notification_idempotency", "notification_jobs",
                    ["deployment", "owner", "request_key"], unique=True, schema=schema)
    op.create_index("ix_notification_queue", "notification_jobs",
                    ["deployment", "status", "available_at"], schema=schema)
    op.create_table(
        "notification_rate_gates",
        required("deployment", sa.String(200), primary_key=True),
        required("key", sa.String(32), primary_key=True),
        required("available_at", sa.DateTime(timezone=True)),
        schema=schema,
    )


def downgrade():
    schema = "notifications" if op.get_bind().dialect.name == "postgresql" else None
    op.drop_table("notification_jobs", schema=schema)
    op.drop_table("notification_rate_gates", schema=schema)
