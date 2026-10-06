"""Per-user file storage metadata and durable blob cleanup."""

from alembic import op
import sqlalchemy as sa

revision = "20260930_06"
down_revision = "20260929_05"
branch_labels = None
depends_on = None


def upgrade():
    postgres = op.get_bind().dialect.name == "postgresql"
    schema = "file_storage" if postgres else None
    prefix = "file_storage." if postgres else ""
    auth = "auth." if postgres else ""
    if postgres:
        op.execute("CREATE SCHEMA IF NOT EXISTS file_storage")

    def required(name, type_, **kwargs):
        return sa.Column(name, type_, nullable=False, **kwargs)

    op.create_table(
        "storage_blobs",
        required("id", sa.String(36), primary_key=True),
        required("deployment", sa.String(64)),
        required("owner_id", sa.String(36)),
        required("size", sa.BigInteger()),
        required("state", sa.String(20)),
        required("created_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["owner_id"], [auth + "users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("deployment", "owner_id", "id", name="uq_storage_blob_owner"),
        sa.CheckConstraint("state IN ('uploading', 'ready', 'pending_delete')", name="ck_storage_blob_state"),
        sa.CheckConstraint("size >= 0", name="ck_storage_blob_size"),
        schema=schema,
    )
    op.create_index("ix_storage_blob_cleanup", "storage_blobs", ["deployment", "state", "created_at"], schema=schema)
    op.create_table(
        "storage_entries",
        required("id", sa.String(36), primary_key=True),
        required("deployment", sa.String(64)),
        required("owner_id", sa.String(36)),
        sa.Column("parent_id", sa.String(36)),
        required("name", sa.String(255)),
        required("kind", sa.String(10)),
        sa.Column("blob_id", sa.String(36)),
        required("size", sa.BigInteger()),
        sa.Column("content_type", sa.String(255)),
        required("created_at", sa.DateTime(timezone=True)),
        required("updated_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("trash_root_id", sa.String(36)),
        sa.ForeignKeyConstraint(["owner_id"], [auth + "users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("deployment", "owner_id", "id", name="uq_storage_entry_owner"),
        sa.ForeignKeyConstraint(["deployment", "owner_id", "parent_id"],
                                [prefix + "storage_entries." + col for col in ("deployment", "owner_id", "id")],
                                name="fk_storage_parent", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["deployment", "owner_id", "blob_id"],
                                [prefix + "storage_blobs." + col for col in ("deployment", "owner_id", "id")],
                                name="fk_storage_blob"),
        sa.CheckConstraint("(kind = 'folder' AND blob_id IS NULL AND size = 0) OR "
                           "(kind = 'file' AND blob_id IS NOT NULL AND size >= 0)", name="ck_storage_entry_kind"),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_storage_parent_self"),
        sa.CheckConstraint("(deleted_at IS NULL AND trash_root_id IS NULL) OR "
                           "(deleted_at IS NOT NULL AND trash_root_id IS NOT NULL)", name="ck_storage_trash"),
        schema=schema,
    )
    for name, columns, predicate in (
        ("uq_storage_root_name", ["deployment", "owner_id", "name"], "parent_id IS NULL AND deleted_at IS NULL"),
        ("uq_storage_child_name", ["deployment", "owner_id", "parent_id", "name"], "parent_id IS NOT NULL AND deleted_at IS NULL"),
    ):
        op.create_index(name, "storage_entries", columns, unique=True, schema=schema,
                        postgresql_where=sa.text(predicate), sqlite_where=sa.text(predicate))
    op.create_index("ix_storage_entries_owner", "storage_entries", ["deployment", "owner_id", "parent_id"], schema=schema)


def downgrade():
    schema = "file_storage" if op.get_bind().dialect.name == "postgresql" else None
    op.drop_table("storage_entries", schema=schema)
    op.drop_table("storage_blobs", schema=schema)
