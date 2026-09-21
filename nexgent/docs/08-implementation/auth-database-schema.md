# Auth Database Schema

Date: 2026-09-17

Integration update (2026-09-17): deployment and frontend instructions below are historical. Use [Unified App Authentication](unified-app-authentication.md) for current startup and feature protection. The separate account Compose file, auth-mode switches and `infra/identity` helpers have been removed; settings now live in `backend/dev.env` or `backend/prod.env`.

Deployment update (2026-09-17): PostgreSQL is now external-only, configured through `NEXGENT_DATABASE_URL`. See [External PostgreSQL Configuration](external-postgresql-configuration.md); the stack no longer includes a database service.

Account storage now uses the PostgreSQL `auth` schema. This updates the earlier [simple login and access control](simple-login-access-control.md) implementation without adding tables or changing account behavior.

## Implementation

All account objects live in `auth`:

- `auth.users`
- `auth.groups`
- `auth.roles`
- `auth.permissions`
- `auth.user_groups`
- `auth.user_roles`
- `auth.group_roles`
- `auth.role_permissions`
- `auth.alembic_version` (migration bookkeeping)

[SQLAlchemy models](../../backend/app/identity/models.py) declare schema-qualified tables and foreign keys. Runtime SQL explicitly addresses `auth`, independent of the connection's search path. Index names remain unchanged.

The [migration runner](../../backend/migrations/env.py) creates `auth` transactionally before Alembic initializes its version table. Fresh installations run historical migrations with a transaction-local `auth` search path, so account tables are never created in `public`. Autogeneration is limited to the `auth` schema.

[Revision 20260917_03](../../backend/migrations/versions/20260917_03_auth_schema.py) moves existing account tables from `public` using `ALTER TABLE ... SET SCHEMA auth`. This preserves data, IDs, password hashes, token versions, foreign keys, indexes and assignments. The runner also relocates the historical Alembic version table. Existing logins remain valid when upgrading revision 02 with the same signing key.

Revision-01 installations complete the earlier simplification migration first; that earlier migration still requires setting local passwords for imported identity-provider accounts. New revision-03 schema movement does not introduce another password reset.

Historical migration files remain intact. SQLite tests translate `auth` to SQLite's main namespace; actual schema placement and cross-schema behavior are tested on PostgreSQL.

## Run / upgrade

Use the existing database selected by the required `NEXGENT_DATABASE_URL`. See [External PostgreSQL Configuration](external-postgresql-configuration.md); there is no bundled database service. Its owner can create the `auth` schema. A separately managed migration role needs database CREATE permission, ownership of the existing tables, and access to `auth`; an independently configured runtime role needs USAGE on `auth` and table permissions. The supplied Compose setup uses the same configured URL for migration and runtime and does not provision roles or databases.

Back up an existing account database before upgrading. From the repository root with the stack running:

```bash
# Bash: NEXGENT_DATABASE_URL must be exported in this shell.
pg_dump "${NEXGENT_DATABASE_URL/postgresql+psycopg:/postgresql:}" > /tmp/nexgent-before-auth-schema.sql
docker compose --env-file infra/identity/.env -f compose.accounts.yaml up --build -d --remove-orphans
```

The one-shot migration service runs `alembic upgrade head` before the backend starts. With dependencies installed and `NEXGENT_DATABASE_URL` configured, the standalone equivalent from `backend/` is:

```bash
uv run alembic upgrade head
uv run alembic current
```

Inspect the deployed schema (Bash, with `NEXGENT_DATABASE_URL` exported; the replacement removes the SQLAlchemy driver suffix for PostgreSQL CLI tools):

```bash
psql "${NEXGENT_DATABASE_URL/postgresql+psycopg:/postgresql:}"
```

Inside psql:

```text
\dt auth.*
\d auth.users
\d auth.role_permissions
SELECT version_num FROM auth.alembic_version;
```

Expected revision: `20260917_03`. Detailed fields and relationships are in the [schema reference](../05-data/identity-access-database-plan.md).

The runner rejects ambiguous histories in both schemas, or an unrecognized public migration history, instead of guessing which records to move. Name collisions during table moves also fail transactionally. Unrelated public tables are untouched. Resolve such conflicts before retrying; the implementation does not merge two installations.

Revision 03 can be downgraded to revision 02 to move the eight application tables back to `public`; bookkeeping remains in `auth`, and the runner supports upgrading again. This is only for rollback with the prior application code. Downgrading the earlier simplification revision still requires a backup restore. The migration never drops either schema.

## Validation

- Full backend regression run: 82 passed, 2 skipped. The skips require PostgreSQL schemas/row locks.
- Final targeted SQLite schema comparison and data-preservation checks: passed.
- PostgreSQL 18.6 account suite: 45 passed, covering fresh `auth` creation, an empty public account namespace, all foreign keys pointing into `auth`, preservation from public revisions 01 and 02, repeat upgrades, revision-03 downgrade/re-upgrade, and normal login/authorization/concurrent last-admin behavior.
- A fresh installation with an unrelated `public.users` table verifies explicit runtime qualification and preservation of that unrelated table.
- Offline PostgreSQL migration SQL generation: passed.

Commands from `backend/`:

```bash
.venv/bin/python -m pytest -q
NEXGENT_TEST_DATABASE_URL='postgresql+psycopg:///postgres?host=/tmp/nexgent-simple-auth-pg&port=55439' .venv/bin/python -m pytest tests/identity -q
NEXGENT_DATABASE_URL=postgresql+psycopg://nexgent:test@localhost/nexgent .venv/bin/alembic upgrade head --sql > /tmp/nexgent-auth-schema.sql
```

The PostgreSQL URL above points to the isolated temporary cluster used for validation. It has no TCP listener and is stopped after testing. The test fixture creates/drops only randomly named test databases; use a dedicated test cluster when rerunning it. Existing FastAPI/Python 3.14 deprecation warnings remain.

## Remaining deployment verification

This change has not migrated an existing deployed database. Docker daemon access is unavailable to the current OS account, so connectivity to the configured external database and the deployed browser flow remain unverified. No frontend files changed.

With Docker access, run the upgrade commands above, then:

```bash
docker compose --env-file infra/identity/.env -f compose.accounts.yaml exec backend alembic current
psql "${NEXGENT_DATABASE_URL/postgresql+psycopg:/postgresql:}" -c '\dt auth.*'
python3 infra/identity/smoke.py --login
```

The smoke check prompts privately for an existing administrator's credentials and signs that account out on all devices.
