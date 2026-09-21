"""Replace identity-provider scaffolding with local users and simple RBAC.

Existing user IDs/profiles and active/suspended state are preserved.
External passwords cannot be imported: those users need administrator resets.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260917_02"
down_revision = "20260917_01"
branch_labels = None
depends_on = None

ADMIN_ROLE = "00000000-0000-0000-0000-000000000001"
ADMIN_PERMISSION = "00000000-0000-0000-0000-000000000002"


def upgrade():
    op.add_column("users", sa.Column("username", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    # Deterministic unique usernames preserve profiles without trusting email uniqueness.
    op.execute("UPDATE users SET username = 'user-' || replace(id, '-', '')")
    op.execute("UPDATE users SET is_active = false WHERE id IN (SELECT user_id FROM memberships WHERE status = 'suspended')")
    with op.batch_alter_table("users") as batch:
        batch.alter_column("username", existing_type=sa.String(64), nullable=False)
        batch.create_unique_constraint("uq_users_username", ["username"])
        batch.create_check_constraint("user_token_version", "token_version >= 0")

    op.create_table("groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.String(500), nullable=False))
    op.create_table("roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False))
    op.create_table("permissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False))
    for table, left, left_table, right, right_table in (
        ("user_groups", "user_id", "users", "group_id", "groups"),
        ("user_roles", "user_id", "users", "role_id", "roles"),
        ("group_roles", "group_id", "groups", "role_id", "roles"),
        ("role_permissions", "role_id", "roles", "permission_id", "permissions"),
    ):
        op.create_table(table,
            sa.Column(left, sa.String(36), sa.ForeignKey(f"{left_table}.id", ondelete="CASCADE"), primary_key=True),
            sa.Column(right, sa.String(36), sa.ForeignKey(f"{right_table}.id", ondelete="CASCADE"), primary_key=True))
        op.create_index(f"ix_{table}_{right}", table, [right])

    roles = sa.table("roles", sa.column("id", sa.String(36)), sa.column("name", sa.String(100)), sa.column("description", sa.String(500)), sa.column("is_system", sa.Boolean()))
    permissions = sa.table("permissions", sa.column("id", sa.String(36)), sa.column("key", sa.String(100)), sa.column("description", sa.String(500)), sa.column("is_system", sa.Boolean()))
    op.bulk_insert(roles, [{"id": ADMIN_ROLE, "name": "Administrator",
                           "description": "Create accounts and manage all access settings", "is_system": True}])
    op.bulk_insert(permissions, [{"id": ADMIN_PERMISSION, "key": "access.manage",
                                 "description": "Create accounts and manage users, groups, roles and permissions",
                                 "is_system": True}])
    op.execute(sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role, :permission)")
               .bindparams(role=ADMIN_ROLE, permission=ADMIN_PERMISSION))
    op.execute(sa.text("INSERT INTO user_roles (user_id, role_id) SELECT user_id, :role FROM memberships WHERE role = 'owner'")
               .bindparams(role=ADMIN_ROLE))

    for table in ("audit_events", "login_transactions", "app_sessions", "memberships", "identities", "companies"):
        op.drop_table(table)


def downgrade():
    raise RuntimeError("The old identity links were removed. Restore a pre-migration backup to roll back.")
