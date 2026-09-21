# Nexgent Managed Account Foundation

Date: 2026-09-17

Integration update (2026-09-17): deployment and frontend instructions below are historical. Use [Unified App Authentication](unified-app-authentication.md) for current startup and feature protection. The separate account Compose file, auth-mode switches and `infra/identity` helpers have been removed; settings now live in `backend/dev.env` or `backend/prod.env`.

Superseded (2026-09-17): this is the historical record of the earlier implementation. Its Keycloak stack, account/session schema, CLI commands and security screens have been replaced. Use [Simple Login and Access Control](simple-login-access-control.md) for current code, startup commands and validation.

Status: initial implementation slice (phase 1a). Automated application tests pass; live container, PostgreSQL, email, MFA, and browser-flow verification remains outstanding because the current OS account cannot access Docker.

## Implemented scope

This starts the [identity/access delivery plan](../07-roadmap/identity-access-delivery-plan.md) with one company and **Nexgent-managed accounts only**. It does not complete the full account-administration or workspace-authorization project.

- Added a separate `compose.accounts.yaml` local stack with PostgreSQL, a Nexgent-operated Keycloak realm, explicit Alembic migration service, FastAPI, the account frontend, and Mailpit for local email capture.
- Added company, user, immutable identity link, membership, application session, login transaction, and audit-event tables. IDs are generated UUIDs stored as `VARCHAR(36)` for the initial portable schema. The deployed database must be PostgreSQL; SQLite is used only by automated tests.
- Added operator-only company/owner bootstrap, member/recovery-owner enrollment, suspension, and restoration. Existing identity subjects are enrolled explicitly; email matching never creates or links an application identity.
- Added Authorization Code + PKCE login through Authlib, browser-bound ten-minute login transactions, single-use callback consumption, nonce/issuer/audience/signature/expiry validation, and verified-email checks.
- Added random opaque application session cookies with only their SHA-256 digests stored in the DB. No access, ID, refresh token, password, or MFA secret is stored in frontend state/localStorage. Upstream tokens are discarded after validation.
- Added live membership checks, request-idle/absolute expiry, session rotation on login, CSRF plus exact-origin validation for mutations, per-user session listing/revocation, and local-first logout followed by the identity-service logout confirmation.
- Added the account sign-in entry, profile, security-management link, active sessions, sign-out, cross-tab sign-out notification, and neutral login/service error states. Managed-account native builds show a browser-use message until native authentication is implemented.
- Added atomic audit events for enrollment, application session creation/revocation, and operator status changes. Keycloak authentication/admin event recording is enabled with a one-day development retention period.
- Patched Vitest from 4.1.10 to 4.1.11 after the repository-required audit reported its mocker dependency advisory. Only npm's package manifest/lockfile are used for these builds; the existing historical pnpm lockfile was not regenerated.

The internal identity protocol is OIDC, but there are no company SSO providers, directory federation, social-login clients, or public registration flows.

## Runtime boundary

`NEXGENT_AUTH_MODE=managed` mounts only account routes and a minimal `/health` endpoint. Everything else requires a valid session and then returns `404` if not registered. Legacy Chat, Nextcloud and RAG routes are deliberately not mounted in this mode because they do not yet enforce resource permissions. The account frontend does not mount legacy feature components or contact their services.

`NEXGENT_AUTH_MODE=legacy` remains the default for the existing development/production stacks. **Those existing stacks are not secured by this change.** This is a separate local development slice, not a migration of running users or workloads. Unknown authentication modes fail startup/build rather than silently selecting a fallback.

The account stack has no agent, RAG, Scout, or report services, mounts no legacy credentials, and exposes no backend/DB ports. Its Nginx config rejects old runtime proxy paths and the identity administration API. Only loopback host ports are published:

| URL | Purpose |
| --- | --- |
| `http://localhost:5180` | Nexgent account UI and authorized account APIs |
| `http://localhost:8181/identity/admin/` | Operator-only local Keycloak administration console |
| `http://localhost:8026` | Local test-email inbox; messages do not go to real recipients |

Use `localhost` consistently: identity issuer, callback, logout and CSRF origin are exact matches. The master realm's authentication endpoints are proxied to allow the separate operator console to log in; its management API remains blocked at the app ingress. None of these local endpoints is an employee deployment.

## Configuration decisions

- The local realm disables registration, implicit grants and password/direct-access grants. The application client requires PKCE S256 and an exact callback URI.
- The development realm requires verified email and OTP setup for every newly created user. This is deliberately stricter than the draft's optional MFA for ordinary members. Actual enrollment/login behavior still needs live verification.
- Local identity/password-reset emails are delivered to Mailpit. Password policy starts at 15 characters, rejects the username, and tracks five prior passwords. Brute-force protection is configured in Keycloak; app login initiation is rate-limited by Nginx.
- Session defaults are 30 minutes of request inactivity and 12 hours absolute. Account-screen polling is request activity and can extend the idle window, never the absolute window.
- HTTPS origins use `__Host-` Secure/HttpOnly/SameSite cookies. HTTP requires both an explicit development flag and a loopback public origin/issuer, and uses distinctly named local cookies. The included realm's HTTP and `start-dev` settings are local-only.
- One PostgreSQL container holds separate identity and application databases owned by separate non-superuser roles. Database connection privileges are not shared. The initial application/migration role still owns its tables; separate runtime/migration/audit DB privileges and RLS are future work.
- Authlib uses fixed endpoints from the configured local realm; public browser and private token/JWK URLs can differ. No user-provided issuer URL is accepted.
- Backend access logging is disabled in the account stack, and Nginx excludes authentication/identity requests from its access log so callback codes and action tokens are not recorded. Keep equivalent protections when adding production logging.
- Operator changes are attributed as `operator.*` audit actions with a null application actor, because the CLI uses OS/deployment authority. Operator identity attribution and externally protected audit export remain future work.

## Start the local account stack

From the repository root, create secrets once. This implementation session already created the ignored `infra/identity/.env`; the generator refuses to overwrite an existing file.

```bash
python3 infra/identity/setup_local.py
docker compose --env-file infra/identity/.env -f compose.accounts.yaml config --quiet
docker compose --env-file infra/identity/.env -f compose.accounts.yaml up --build -d
docker compose --env-file infra/identity/.env -f compose.accounts.yaml ps
```

The generated file has mode `0600` and unique random DB, client, and operator secrets. It is Git-ignored. Obtain the operator password from that file locally; do not paste it into logs, tickets, or CLI arguments. Keep existing secrets when restarting the stack: changing the env file does not rotate passwords in existing PostgreSQL volumes or imported identity realms.

If Docker access is restricted, run the same commands as an authorized Docker operator. No host permissions or group membership were changed by this implementation.

Once the identity service finishes starting:

```bash
python3 infra/identity/smoke.py
```

This checks unauthorized API responses, blocked legacy/admin routes, realm discovery, PKCE redirect, browser login cookie, and the actual identity credential form. It creates one temporary login transaction but no account, message, or application session. It does not verify the complete interactive login flow.

## Bootstrap and enroll accounts

1. Open the operator console at `http://localhost:8181/identity/admin/`, using `account-operator` and the generated operator password.
2. Select the `nexgent` realm, create a local user with an email and display name, and record its immutable user ID. Use the identity console's required-action email flow to request password setup, email verification, and OTP setup. Inspect the resulting email in Mailpit. No real employee mail is sent by this local stack.
3. Bind that exact identity subject to the first application owner using the command below. Credentials remain in the identity service; only identity ID/profile inputs appear in the command.
4. Complete the identity setup actions and sign in through `http://localhost:5180`. A verified identity that has not been enrolled in Nexgent receives no application access.

```bash
docker compose --env-file infra/identity/.env -f compose.accounts.yaml exec backend \
  python -m app.identity.admin bootstrap \
  --company-name 'Example Company' \
  --subject 'USER_ID_FROM_NEXGENT_REALM' \
  --email 'owner@example.test' --name 'Company Owner'
```

Bootstrap fails if a company already exists. Record the returned membership ID for operator account lifecycle commands. After creating additional identities in the same realm:

```bash
docker compose --env-file infra/identity/.env -f compose.accounts.yaml exec backend \
  python -m app.identity.admin add-member \
  --subject 'MEMBER_ID_FROM_NEXGENT_REALM' \
  --email 'member@example.test' --name 'Team Member'

docker compose --env-file infra/identity/.env -f compose.accounts.yaml exec backend \
  python -m app.identity.admin add-owner \
  --subject 'RECOVERY_OWNER_ID_FROM_NEXGENT_REALM' \
  --email 'recovery@example.test' --name 'Recovery Owner'

docker compose --env-file infra/identity/.env -f compose.accounts.yaml exec backend \
  python -m app.identity.admin suspend 'MEMBERSHIP_ID'

docker compose --env-file infra/identity/.env -f compose.accounts.yaml exec backend \
  python -m app.identity.admin restore 'MEMBERSHIP_ID'
```

Suspension blocks application requests and revokes application sessions transactionally; restoration never revives old sessions. The last active owner cannot be suspended. For complete account suspension, disable the corresponding identity in the operator console as well. Application suspension does not yet enqueue an identity-service update.

Stopping preserves the database volume:

```bash
docker compose --env-file infra/identity/.env -f compose.accounts.yaml down
```

Do not apply these commands to the legacy Compose projects. Realm startup import is first-use only: editing the realm JSON does not update an existing realm. Use reviewed identity administration changes or an explicit migration for existing data. [Keycloak realm import behavior](https://www.keycloak.org/server/importExport)

## Validation performed

- Final regression totals: **70 backend tests** (31 new identity cases) and **260 frontend tests** (6 new account cases) passed. Documentation validation checked 55 local links with no errors.
- Backend suite: automated identity tests use a migrated temporary SQLite database and real RSA-signed tokens against mocked HTTP token/JWK endpoints. Covers issuer/audience/signature/nonce/expiry rejection, unverified email, email-linking denial, PKCE, state/cookie binding, transaction expiry/replay, cookie flags, CSRF, session ownership/rotation/expiry/revocation, suspension/restoration, bootstrap and last-owner safeguards, closed legacy routes, and DB failure behavior.
- SQLite migration upgrade and model/schema comparison passed. PostgreSQL-dialect migration SQL generation passed; this does not prove execution on PostgreSQL or concurrent row-lock behavior.
- Frontend account-client and render tests cover credentials/CSRF, unauthenticated versus unavailable states, mutation failures, neutral sign-in errors, and the native-webview guard. Full frontend regression tests and both legacy/managed production builds passed. No browser screenshot or interactive browser test was performed.
- `cargo check` passed using a fresh `/tmp/nexgent-identity-cargo-target` directory. The original cached target referenced a missing historical `workflow-helper` path; no Rust source/configuration was changed to work around it.
- npm audit reported zero vulnerabilities after the Vitest patch. The advisory fixed is [GHSA-82fw-gwwq-j7x9](https://github.com/vitest-dev/vitest/security/advisories/GHSA-82fw-gwwq-j7x9).
- Compose configuration, realm JSON syntax, initialization shell syntax, Python compilation, and Git whitespace checks passed. Generated `.env` is ignored by Git.

Commands to reproduce application checks:

```bash
# backend/
UV_CACHE_DIR=/tmp/nexgent-identity-uv-cache uv sync --extra dev --locked
uv run --extra dev pytest
NEXGENT_DATABASE_URL=postgresql+psycopg://nexgent:test@localhost/nexgent \
  uv run --extra dev alembic upgrade head --sql

# frontend/
npm test -- --run
npm run build
VITE_AUTH_MODE=managed npm run build
CARGO_TARGET_DIR=/tmp/nexgent-identity-cargo-target \
  cargo check --offline --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
```

## Remaining verification and implementation

Docker access failed both inside and outside the sandbox (`permission denied` on `/var/run/docker.sock`); `sudo -n` required interactive authentication. No containers were built or started. The exact remaining deployment verification begins with:

```bash
docker compose --env-file infra/identity/.env -f compose.accounts.yaml up --build -d
python3 infra/identity/smoke.py
docker compose --env-file infra/identity/.env -f compose.accounts.yaml exec backend alembic current
docker compose --env-file infra/identity/.env -f compose.accounts.yaml exec backend alembic check
```

Then execute the bootstrap/enrollment sequence above and verify password setup, email verification, OTP enrollment/challenge, account profile/security console, password reset, two-browser session revocation, logout confirmation, and application suspension. Check migration retry after restart and last-owner/concurrent callback behavior against actual PostgreSQL. Verify the operator-console login/redirect flow and that administration remains unreachable through the application ingress.

Before employee deployment, complete the remaining phase-1 and later gates: People/invitation UI and APIs; durable provisioning/outbox/reconciliation; identity-console suspension/password/MFA-event propagation to app sessions; recent-MFA checks; group/workspace roles and resource registry; workload/tool authorization; connector/RAG access filtering; approvals; production TLS/secret handling and isolated runtime DB privileges; retention/cleanup jobs, protected audit export, and backup/restore exercises. A password change or identity-console disable does **not yet revoke existing Nexgent app sessions**; use the Nexgent operator suspension command for immediate application cutoff.

The frontend account screen is intentionally the only enabled managed feature until workspace authorization exists. Continue implementation from this foundation without enabling legacy routes merely because login now works.
