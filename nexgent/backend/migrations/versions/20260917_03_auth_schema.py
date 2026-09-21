"""Keep account tables in auth, preserving existing public-schema installations."""
from alembic import op

revision = "20260917_03"
down_revision = "20260917_02"
branch_labels = None
depends_on = None

TABLES = ("users", "groups", "roles", "permissions", "user_groups",
          "user_roles", "group_roles", "role_permissions")


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return  # SQLite is only a portable test substitute without schemas.
    # env.py selects public only when continuing a historical installation.
    # Fresh installations already created every table directly in auth.
    for table in TABLES:
        op.execute(f"""DO $$ BEGIN
            IF current_schema() = 'public' THEN
                ALTER TABLE public.{table} SET SCHEMA auth;
            END IF;
        END $$""")
    op.execute("SET LOCAL search_path TO auth")


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    for table in reversed(TABLES):
        op.execute(f"ALTER TABLE auth.{table} SET SCHEMA public")
    op.execute("SET LOCAL search_path TO public")
    # Keep auth/alembic_version for migration bookkeeping and never drop a schema
    # that might contain other objects. env.py recognizes this older table layout.
