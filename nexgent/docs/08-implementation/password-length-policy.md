# Password Length Policy

Date: 2026-09-21

## Implementation

New passwords must contain 4–12 characters inclusive. The shared hashing function
and API creation/reset models enforce the limit. Operator prompts, administration
forms, HTML input constraints, and the client validation message use the same range.
Argon2id storage is unchanged; no database migration is required.

Login retains its existing 1–256 character input range so previously created
accounts with longer passwords can still authenticate. Changing their passwords
requires the new range. Existing test credentials now satisfy the updated policy.

## Operations

Rebuild the affected services when deploying production images, from the project root:

```bash
docker compose -f compose.prod.yaml up -d --build backend frontend
```

For operator account creation:

```bash
docker compose -f compose.prod.yaml exec backend python -m app.identity.admin create-admin --username admin --name "Administrator"
```

## Validation

- Frontend build passed: `cd frontend && npm run build` (bundle-size warning).
- Account client tests passed (5): `cd frontend && npm test -- src/shared/api/accountClient.test.ts`.
- Backend identity tests passed (49 passed, 2 PostgreSQL-only checks skipped):
  `cd backend && env -u NEXGENT_TEST_DATABASE_URL .venv/bin/pytest tests/identity -q`.
  The sandboxed run stalled and was stopped; the successful run used temporary
  SQLite databases outside the sandbox. Tests cover creation/reset acceptance at 4 and 12 characters,
  rejection at 3 and 13, unchanged passwords after rejected resets, and login using
  a previously stored longer password.
- Desktop check could not complete: `cd frontend && cargo check --manifest-path src-tauri/Cargo.toml`
  encountered a cached Tauri permission-file path pointing to the absent
  `workflow-helper` checkout. After repairing that build cache, rerun this command.
- Dependency audit could not complete because registry DNS resolution failed:
  rerun `cd frontend && npm audit --audit-level=moderate` with network access.

No deployed browser/PostgreSQL end-to-end check was performed; the deployment was
not changed. After deployment, verify login against the configured service
(set `NEXGENT_PUBLIC_URL` to the deployed origin; this logs the supplied admin out):

```bash
cd backend
.venv/bin/python smoke_auth.py --origin "$NEXGENT_PUBLIC_URL" --login
```
