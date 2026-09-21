import os

from alembic import context
from sqlalchemy import create_engine, pool

from app.identity.models import Base
from app.chat import persistence  # noqa: F401 -- register chat metadata

url = os.environ["NEXGENT_DATABASE_URL"]
postgresql = url.startswith("postgresql")

# Also emitted in offline SQL so fresh installs and historical upgrades follow
# the same path. All preparation and migrations run in one PostgreSQL transaction.
PREPARE_AUTH = """
DO $$
DECLARE legacy boolean := false;
BEGIN
    IF to_regclass('public.alembic_version') IS NOT NULL THEN
        IF to_regclass('auth.alembic_version') IS NOT NULL THEN
            RAISE EXCEPTION 'Both public and auth migration histories exist; reconcile before upgrading';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM public.alembic_version
                       WHERE version_num IN ('20260917_01', '20260917_02'))
           OR EXISTS (SELECT 1 FROM public.alembic_version
                      WHERE version_num NOT IN ('20260917_01', '20260917_02')) THEN
            RAISE EXCEPTION 'Unrecognized public migration history; refusing to move it';
        END IF;
        ALTER TABLE public.alembic_version SET SCHEMA auth;
        legacy := true;
    ELSIF to_regclass('auth.alembic_version') IS NOT NULL THEN
        SELECT EXISTS (SELECT 1 FROM auth.alembic_version
                       WHERE version_num IN ('20260917_01', '20260917_02'))
               AND to_regclass('public.users') IS NOT NULL
               AND to_regclass('auth.users') IS NULL INTO legacy;
    END IF;
    IF legacy THEN
        SET LOCAL search_path TO public;
    ELSE
        SET LOCAL search_path TO auth;
        -- After the explicit-schema migration, use the neutral default for
        -- reflection. Otherwise PostgreSQL omits auth from cross-schema FKs
        -- and Alembic incorrectly proposes replacing valid chat ownership FKs.
        IF to_regclass('auth.alembic_version') IS NOT NULL THEN
            IF EXISTS (SELECT 1 FROM auth.alembic_version
                       WHERE version_num NOT IN ('20260917_01', '20260917_02')) THEN
                SET LOCAL search_path TO public;
            END IF;
        END IF;
    END IF;
END $$
"""

def include_name(name, type_, _parent_names):
    return type_ != "schema" or name in {"auth", "chat"}


options = dict(target_metadata=Base.metadata, compare_type=True,
               include_schemas=postgresql, version_table_schema="auth" if postgresql else None)
if postgresql:
    options["include_name"] = include_name

if context.is_offline_mode():
    context.configure(url=url, literal_binds=True, **options)
    with context.begin_transaction():
        if postgresql:
            context.execute("CREATE SCHEMA IF NOT EXISTS auth")
            context.execute(PREPARE_AUTH)
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    with engine.begin() as connection:
        if postgresql:
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(117984, 1)")
            connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS auth")
            connection.exec_driver_sql(PREPARE_AUTH)
        context.configure(connection=connection, **options)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
