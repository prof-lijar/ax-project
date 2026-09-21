# Nexgent Login and Access Backend and UI Plan

Date: 2026-09-17

Scope revision (2026-09-17): simple login and administrator-managed accounts/groups/roles/permissions. This replaces the earlier identity-provider and workspace rollout. Code is implemented; validation and remaining runtime checks are recorded in [Unified app authentication](../08-implementation/unified-app-authentication.md).

## Backend

Keep a single `backend/app/identity/` package:

| Module | Responsibility |
| --- | --- |
| config.py | Required database URL, public origin, signing key, cookie lifetime |
| models.py | Eight-table SQLAlchemy schema |
| security.py | Argon2 password hashing, signed cookies, CSRF token derivation |
| store.py | Account lookup, live permissions, transactional admin operations |
| router.py | Request validation, authentication boundary, permission checks, safe errors |
| admin.py | Interactive first-admin creation and operator password reset |

No separate provisioning worker, identity provider, mail service, or session store.

## HTTP API

| Method | Route | Access / behavior |
| --- | --- | --- |
| GET | /health | Public process health; startup checks migrated DB |
| POST | /auth/login | Public; username/password, exact Origin; sets cookie |
| POST | /auth/logout | Authenticated + CSRF; invalidates all current user's logins |
| GET | /api/me | Authenticated profile, roles, effective permissions, CSRF token |
| GET | /api/admin/access | access.manage; users/groups/roles/permissions catalog |
| POST | /api/admin/users | access.manage; create account and assignments |
| PUT | /api/admin/users/{id} | access.manage; replace profile, active state, direct roles and groups |
| PUT | /api/admin/users/{id}/password | access.manage; admin password reset |
| POST / PUT | /api/admin/groups[/{id}] | access.manage; name, description, role_ids |
| POST / PUT | /api/admin/roles[/{id}] | access.manage; name, description, permission_ids |
| POST / PUT | /api/admin/permissions[/{id}] | access.manage; key, description |
| DELETE | /api/admin/{groups,roles,permissions}/{id} | access.manage; delete custom definition and assignments |

Authenticated mutations require exact Origin and `X-CSRF-Token`. Inputs reject unknown fields. UUID assignment IDs must refer to existing rows. Assignment lists are bounded to 500 entries. Full updates replace the relevant assignment sets; users have no delete endpoint.

Example create-user JSON, sent only by an authenticated administrator:

```json
{
  "username": "jane",
  "name": "Jane",
  "email": "jane@example.com",
  "password": "<administrator-provided password>",
  "role_ids": [],
  "group_ids": []
}
```

For user updates omit username/password and include `is_active`. For a password reset send only `password`. API errors return `{"error":{"code":"..."}}` without reflecting credentials. Typical statuses: 401 missing/invalid login, 403 denied/origin/CSRF, 404 missing record, 409 duplicate/protected definition/last admin, 422 invalid fields/assignments, 503 unavailable database.

## Frontend

The main browser app has these views:

- **Sign in:** username and password, accessible errors, no signup or SSO choices, contact-admin recovery guidance.
- **Main app:** existing feature pages, available after login.
- **Settings / Account:** name, username, roles, effective permissions, and “Sign out all devices.”
- Administrators additionally see **Manage access**, with Users, Groups, Roles, Permissions sections.

Admin operations:

| Section | UI |
| --- | --- |
| Users | Create account; edit name/email; activate/disable; assign groups/direct roles; reset password; inspect effective permissions |
| Groups | Create/edit/delete; select roles inherited by members |
| Roles | Create/edit/delete custom roles; select permissions |
| Permissions | Create/edit/delete custom permission keys; describe their intended use |

Built-in definitions are marked read-only. Deletion requires inline confirmation that assignments will be removed. Failed last-admin changes explain the requirement and preserve the current database state.

The API adapter owns requests. Passwords are read from uncontrolled forms, sent directly, and cleared on submission. They are never placed in React state, TanStack Query caches, or localStorage. Profile data refreshes every 30 seconds and on focus; server authorization is evaluated on every request. Logout clears cached access data, and lost admin permissions remove the admin view.

## Verification and delivery

1. Run migrations against a fresh database and the existing revision-01 fixture; compare final schema with models.
2. Test login, cookie/signature validation, Origin/CSRF enforcement and password handling.
3. Test all admin routes as both administrator and ordinary user.
4. Test direct/group permission union and immediate revocation.
5. Test last-admin protection, including concurrent PostgreSQL edits.
6. Test API adapter and UI rendering; build the single authenticated frontend.
7. Start the Compose stack, create the first admin interactively, and run the HTTP smoke check.
8. Manually verify login and complete admin CRUD in a browser.

## Current limits and later extensions

This is a small-company catalog UI, without search/pagination, account self-service, per-device sessions, or a persistent audit history. Its access mutations serialize on one row, an intentional tradeoff for a simple correct last-admin invariant.

All current feature routes require login. Future feature-specific authorization uses `Depends(require_permission("feature.action"))`; custom permission records alone do not enforce those keys. No additional domain tables or company SSO are scheduled by this change.
