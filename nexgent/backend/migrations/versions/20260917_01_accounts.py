"""Managed account and session foundation."""
from alembic import op
import sqlalchemy as sa

revision = "20260917_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("companies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.CheckConstraint("key = 'company'", name="single_company_key"))
    op.create_table("users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.UniqueConstraint("issuer", "subject", name="uq_identity_subject"))
    op.create_table("memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.CheckConstraint("role in ('owner', 'member')", name="membership_role"),
        sa.CheckConstraint("status in ('active', 'suspended')", name="membership_status"))
    op.create_table("app_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("membership_id", sa.String(36), sa.ForeignKey("memberships.id"), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_app_sessions_membership_id", "app_sessions", ["membership_id"])
    op.create_index("ix_app_sessions_expires_at", "app_sessions", ["expires_at"])
    op.create_table("login_transactions",
        sa.Column("token_digest", sa.String(64), primary_key=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("nonce", sa.String(100), nullable=False),
        sa.Column("return_to", sa.String(1000), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_login_transactions_expires_at", "login_transactions", ["expires_at"])
    op.create_table("audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("memberships.id")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_audit_events_company_id", "audit_events", ["company_id"])


def downgrade():
    for table in ("audit_events", "login_transactions", "app_sessions", "memberships",
                  "identities", "users", "companies"):
        op.drop_table(table)
