# External PostgreSQL Configuration

Date: 2026-09-17

Integration update (2026-09-17): deployment and frontend instructions below are historical. Use [Unified App Authentication](unified-app-authentication.md) for current startup and feature protection. The separate account Compose file, auth-mode switches and `infra/identity` helpers have been removed; settings now live in `backend/dev.env` or `backend/prod.env`.

The account stack uses an existing PostgreSQL database exclusively. `NEXGENT_DATABASE_URL` is its only database configuration variable. No bundled database, automatic provisioning, or database fallback is supported.

## Implemented changes

- Removed the `accounts-db` service, database volume declaration, PostgreSQL image and database health dependency from `compose.accounts.yaml`.
- Removed `infra/identity/init-databases.sh`; Nexgent no longer creates a PostgreSQL server, database or database role.
- Both the migration and backend services receive the supplied `NEXGENT_DATABASE_URL` unchanged. Compose rejects missing or empty values before startup.
- Removed `ACCOUNT_POSTGRES_PASSWORD` and `ACCOUNT_DB_PASSWORD` generation and their obsolete entries in the ignored local environment file.
- Cleanup update (2026-09-17): also removed obsolete `IDENTITY_DB_PASSWORD`, `ACCOUNT_CLIENT_SECRET`, and `ACCOUNT_OPERATOR_PASSWORD` entries from the ignored local environment file. The existing `ACCOUNT_SIGNING_KEY` was preserved; `NEXGENT_DATABASE_URL` still needs to be supplied.
- `setup_local.py` now generates only `ACCOUNT_SIGNING_KEY`, the separate login-cookie signing secret. It does not generate, guess or alter database connection details.
- Added `infra/identity/example.env` (removed) as the connection-format reference and updated current startup/schema documentation.

The three services are `migrate`, `backend` and `frontend`. The backend still waits for migration success. A failed database connection or migration stops startup; it does not start another database.

## Configure and start

Set this in the ignored `infra/identity/.env` file, using your actual existing database:

```dotenv
NEXGENT_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@DB_HOST:5432/DB_NAME
```

The host must be reachable from the Docker containers. `localhost` inside a container refers to that container. URL-encode special characters in usernames/passwords; PostgreSQL connection options, such as `?sslmode=require`, can be included in the URL.

The database must already exist. The configured migration role needs permission to create the `auth` schema and its tables, or the necessary rights on an existing `auth` schema. Moving older public-schema tables also requires ownership of those tables. No separate schema environment variable is needed: runtime models explicitly use `auth`.

The login signing key remains independent of database configuration. Generate it without changing an existing key or URL:

```bash
python3 infra/identity/setup_local.py
docker compose --env-file infra/identity/.env -f compose.accounts.yaml config --quiet
docker compose --env-file infra/identity/.env -f compose.accounts.yaml up --build -d --remove-orphans
docker compose --env-file infra/identity/.env -f compose.accounts.yaml exec backend python -m app.identity.admin create-admin --username admin --name "Administrator"
```

Open http://localhost:5180. The initial-admin command prompts privately for its password; skip it if that account already exists. Protect and back up an existing account database before applying migrations.

No actual external URL was supplied during this change, so no connection value was invented and no external database migration was run. Fill in the URL before starting.

## Existing deployments

No running containers or database volumes were changed by this code edit. If the previous bundled database contains needed data, transfer it to the chosen external database before using `--remove-orphans`, which removes retired containers. The new Compose file does not delete the old database volume and does not perform data transfer automatically.

For direct backend execution, export `NEXGENT_DATABASE_URL` with the same format and configure the normal authentication settings from [backend/example.env](../../backend/example.env). No alternate database environment variables are used.

## Validation

Configuration checks passed with a temporary, non-secret test URL:

- Resolved Compose contains exactly `migrate`, `backend`, `frontend` and no database volume.
- Backend and migration receive the exact URL, including an encoded password and TLS query option.
- Missing and empty URLs both fail Compose configuration.
- Migration has no local-database dependency; backend still requires successful migration completion.
- The helper generates only the signing key with file mode 0600 and preserves existing signing keys and supplied URLs on repeat runs.
- `git diff --check` passed.

No application/schema logic or frontend code changed, so prior application test results remain applicable. Live container startup and connectivity to the user's external PostgreSQL server were not verified: Docker access is unavailable and the connection URL has not been supplied.

After configuring the real URL and starting the stack, complete the remaining checks:

```bash
docker compose --env-file infra/identity/.env -f compose.accounts.yaml ps
docker compose --env-file infra/identity/.env -f compose.accounts.yaml exec backend alembic current
python3 infra/identity/smoke.py --login
```

Expected schema revision: `20260917_03`. The smoke check prompts for an existing admin login and signs that account out on all devices.
