# Simple Login and Access Control

Date: 2026-09-17

Password policy update (2026-09-21): the original 12–256 character creation/reset limit described below has been replaced with 4–12 characters. Existing passwords still work for login. See [Password Length Policy](password-length-policy.md).

Integration update (2026-09-17): deployment and frontend instructions below are historical. Use [Unified App Authentication](unified-app-authentication.md) for current startup and feature protection. The separate account Compose file, auth-mode switches and `infra/identity` helpers have been removed; settings now live in `backend/dev.env` or `backend/prod.env`.

Deployment update (2026-09-17): PostgreSQL is now external-only, configured through `NEXGENT_DATABASE_URL`. See [External PostgreSQL Configuration](external-postgresql-configuration.md); the stack no longer includes a database service.

Schema update (2026-09-17): account tables and Alembic version tracking now use `auth`. See [Auth Database Schema](auth-database-schema.md) for revision 03, migration compatibility and current schema validation.

Implemented: a local username/password login and administrator-managed users, groups, roles and permissions. This supersedes the [earlier managed-account foundation](managed-account-foundation.md).

## What changed

- Replaced external identity-provider authentication with pwdlib Argon2id password verification and PyJWT signed HttpOnly cookies.
- Reduced the database to eight application tables: users, groups, roles, permissions, user_groups, user_roles, group_roles, role_permissions.
- Added admin account creation, profile edits, activation/disabling, password resets, and group/role/permission CRUD with assignment forms.
- Added direct-role and group-role permission union, live permission checks, and a protected built-in Administrator role granting `access.manage`.
- Added a transactionally enforced last-admin invariant. All admin changes serialize on the built-in role row and recheck current actor permissions/version.
- Removed companies, identity links, memberships, app sessions, login transactions and audit-event tables through a forward migration. Broader tables from the earlier plan were never implemented.
- Removed Keycloak, Mailpit, realm configuration, OIDC/Authlib code, redirects, session/security screens, and identity-service proxying from the current stack.
- Local Compose now contains only a one-shot migration, FastAPI and the web frontend. PostgreSQL must already exist and is configured solely with `NEXGENT_DATABASE_URL`. See [External PostgreSQL Configuration](external-postgresql-configuration.md).
- Rewrote the architecture, detailed schema and delivery documents for the simpler scope.

No registration, invitations, company SSO, MFA, email workflow, self-service password recovery, workspace/resource policy, delegation, or provisioning process is included.

## Source map

| Area | Source |
| --- | --- |
| Detailed field/constraint reference | [Database schema](../05-data/identity-access-database-plan.md) |
| SQLAlchemy models | [models.py](../../backend/app/identity/models.py) |
| Schema refactor / data conversion | [revision 20260917_02](../../backend/migrations/versions/20260917_02_simple_access.py) |
| Authorization and transactions | [store.py](../../backend/app/identity/store.py) |
| HTTP routes and request boundary | [router.py](../../backend/app/identity/router.py) |
| Password/cookie helpers | [security.py](../../backend/app/identity/security.py) |
| Operator bootstrap/recovery | [admin.py](../../backend/app/identity/admin.py) |
| Frontend login and administration | [AccountApp.tsx](../../frontend/src/features/accounts/AccountApp.tsx) |
| Frontend API adapter | [accountClient.ts](../../frontend/src/shared/api/accountClient.ts) |
| Local deployment | `compose.accounts.yaml` (removed) |

## Architecture and security decisions

Passwords are 12–256 characters and stored as Argon2id hashes. No default account/password is seeded. Unknown usernames still perform password verification against a dummy hash. Responses and request-validation errors never include password inputs or hashes.

Login cookies expire after eight hours by default; `NEXGENT_LOGIN_SECONDS` allows 300–86400 seconds. A server-side signing key of at least 32 bytes is required. Generated local keys use 48 random bytes encoded as URL-safe text. Cookies are HttpOnly and SameSite=Lax, with Secure and a `__Host-` name under HTTPS. Only explicitly enabled loopback HTTP development uses the non-Secure cookie.

There is no session table. Each request verifies the signature, algorithm, required claims, issuer, audience and expiry, then loads the current active user and checks `token_version`. Logout, password reset and activation-state changes increment that version. Logout therefore affects all devices; there is no per-device logout or sliding refresh.

Origin validation applies to login and all other mutations. Authenticated mutations also need the CSRF value returned by `GET /api/me`, which is derived from the current cookie. Nginx rate-limits login by source IP at 10 requests/minute with burst 5, returning 429. The local backend is not published separately. Non-Compose deployments need equivalent ingress protection.

All admin APIs require `access.manage`; UI controls are not the security boundary. A custom role can grant that permission directly or through a group. Built-in role/permission definitions cannot be edited or deleted through the API. Permission records alone do not secure future endpoints: each feature must enforce its key.

Changes that would leave no active password-enabled administrator roll back. This covers disabling/removing an admin role, membership edits, deleting groups/custom roles, and removing their permissions. PostgreSQL row locking prevents two concurrent requests from each removing the remaining administrator.

Passwords are read from uncontrolled browser fields and submitted directly, never stored in React state, query caches or browser storage. Forms clear password fields on submission. Responses are not cached, and account state refreshes on focus/every 30 seconds.

## Run locally

From the repository root:

```bash
python3 infra/identity/setup_local.py
# Set NEXGENT_DATABASE_URL in infra/identity/.env before starting.
docker compose --env-file infra/identity/.env -f compose.accounts.yaml up --build -d --remove-orphans
docker compose --env-file infra/identity/.env -f compose.accounts.yaml exec backend python -m app.identity.admin create-admin --username admin --name "Administrator"
```

The bootstrap command prompts privately for a password and confirmation. Open **http://localhost:5180**, sign in, then create accounts in **Users**. Use **Permissions → Roles → Groups/Users** to define and assign access.

The setup script generates only the login signing key in owner-only ignored `infra/identity/.env`. Add the required `NEXGENT_DATABASE_URL` for your existing PostgreSQL database to that file. No database passwords, server, database, or user are generated. Never commit this file.

Compose has no database service or database volume. `--remove-orphans` removes retired service containers from the project. If an older bundled database was used, transfer its data to the intended external database before removing that container; its old volume is not deleted by this configuration change.

Operator password recovery:

```bash
docker compose --env-file infra/identity/.env -f compose.accounts.yaml exec backend python -m app.identity.admin set-password --username admin
```

That invalidates all earlier logins for the account. The CLI is a trusted operator path; normal account management uses the authenticated admin UI/API.

## Upgrade an existing account database

Before running the new migration, save a pre-migration backup:

```bash
# Bash: NEXGENT_DATABASE_URL must be exported in this shell.
pg_dump "${NEXGENT_DATABASE_URL/postgresql+psycopg:/postgresql:}" > /tmp/nexgent-before-simple-access.sql
```

Secure that backup because it contains account/identity records. Confirm its contents before proceeding. Revision 02 preserves user IDs, profiles, creation dates and suspended state. Prior owners receive the built-in Administrator role. Usernames become `user-` plus the UUID without hyphens. Password hashes remain null, so imported users cannot log in until reset by an administrator/operator.

Create a new administrator using the command above, or set a local password for an active migrated owner. Then reset imported user passwords in the UI; inactive users also need activation.

Revision 01 is retained as migration history. Revision 02 drops old identity/session/audit records. Downgrade deliberately fails: rollback requires restoring the pre-migration database backup with the previous application version. No unrelated database is deleted by the account migrations.

## Runtime boundary and limitations

`NEXGENT_AUTH_MODE=managed` serves only the account/admin API. `VITE_AUTH_MODE=managed` builds the matching browser frontend. Account mode in a Tauri webview shows a browser-use message.

Existing default development/production stacks remain in legacy mode; their Chat, Nextcloud, RAG and agent integrations have not gained access enforcement through this change. Connect them only after their backend permission checks are implemented.

The first version has a complete small-company access catalog, without pagination/search, persistent audit history, password-change-at-first-login, individual-device sessions or self-service profile/password changes. Administrator-created passwords must be delivered to users through the company's chosen private channel. A single database row serializes access changes; concurrent edits use last successful write rather than optimistic version checking.

## Validation performed

- Full backend suite: **81 passed, 1 skipped**. The skip is the PostgreSQL-only concurrency test in the default SQLite run.
- Identity suite on a fresh, private PostgreSQL **18.6** cluster: **43 passed**, including real migrations, model/schema comparison, legacy profile/owner/suspension preservation, CRUD, inherited permission revocation, Origin/CSRF, cookie/signature failures, password reset/logout invalidation and concurrent last-admin protection.
- PostgreSQL offline migration SQL generation: passed.
- Frontend suite: **263 passed** across 25 test files.
- Both legacy and managed frontend builds: passed. Legacy build retains the existing large-chunk warning.
- Rust `cargo check`: passed using an isolated target directory to avoid the pre-existing cached old project path.
- `npm audit --audit-level=moderate`: **0 vulnerabilities**.
- Secret setup and `docker compose ... config --quiet`: passed.
- Backend tests emit existing FastAPI/Python 3.14 deprecation warnings.

Commands:

```bash
cd backend
UV_CACHE_DIR=/tmp/nexgent-identity-uv-cache uv sync --extra dev --locked
.venv/bin/python -m pytest -q
NEXGENT_DATABASE_URL=postgresql+psycopg://nexgent:test@localhost/nexgent .venv/bin/alembic upgrade head --sql > /tmp/nexgent-simple-auth.sql
```

To run the PostgreSQL-specific tests, supply a **dedicated test cluster** maintenance URL whose user can create/drop databases. The fixture creates fresh randomly named `nexgent_test_*` databases and drops them after each test. It does not run migrations in the supplied maintenance database.

```bash
NEXGENT_TEST_DATABASE_URL='postgresql+psycopg:///postgres?host=/tmp/nexgent-simple-auth-pg&port=55439' .venv/bin/python -m pytest tests/identity -q
```

The private cluster used for this validation had no TCP listener and was stopped after the test run. Adjust the URL for your dedicated test cluster.

From `frontend/`:

```bash
npm test
npm run build
VITE_AUTH_MODE=managed npm run build
CARGO_TARGET_DIR=/tmp/nexgent-identity-cargo-target cargo check --offline --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
```

## Remaining verification

The local OS account cannot access the Docker daemon. Compose image startup, connectivity to your configured external PostgreSQL database, Nginx behavior/rate limiting, Python 3.12 container execution, and an interactive browser CRUD flow have not been verified. The successful PostgreSQL 18.6 tests do not substitute for this deployment check.

With Docker access, from the repository root:

```bash
python3 infra/identity/setup_local.py
# Set NEXGENT_DATABASE_URL in infra/identity/.env before starting.
docker compose --env-file infra/identity/.env -f compose.accounts.yaml up --build -d --remove-orphans
docker compose --env-file infra/identity/.env -f compose.accounts.yaml ps
docker compose --env-file infra/identity/.env -f compose.accounts.yaml exec backend python -m app.identity.admin create-admin --username admin --name "Administrator"
python3 infra/identity/smoke.py --login
```

Skip `create-admin` if that username already exists; use operator password recovery if needed. The smoke check prompts for an existing administrator's credentials, checks login/admin catalog/logout, and signs that administrator out on all devices.

In a browser at http://localhost:5180, create a permission and role, assign that role to a group, create a user in the group, and verify the user's effective permissions. Confirm normal users cannot access administration. Edit/delete the assignments, reset/disable the user, and verify existing logins are rejected. Attempt to disable/remove the final admin and confirm the change is rejected.
