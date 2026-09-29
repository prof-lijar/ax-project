# Signed-In Account Profile in Settings

Date: 2026-09-28 (Asia/Seoul)

## Implementation

Settings now starts with a read-only **Signed-in account / 로그인한 계정** section for both administrators and ordinary members. It shows display name, username, email, account type (administrator/member), and assigned roles. Missing email and empty roles have translated fallback labels; a missing display name falls back to the username.

The profile reads the authenticated `AccountContext`, populated by the existing account API, rather than a selected administrator-management row. No additional request, endpoint, credential storage, or permissions are introduced. CSRF tokens and other authentication internals are not rendered. Account values are displayed as supplied; only interface labels are translated.

The Settings heading is shared by all accounts. Language selection and existing account actions remain available; access management stays restricted to administrators. The profile uses a definition list with two responsive columns and a single-column layout below 640px. Long names, addresses, and role lists wrap. It uses existing tokens and CSS modules without nested cards.

Changed files:

- `frontend/src/features/accounts/AccountApp.tsx`
- `frontend/src/features/accounts/AccountApp.module.css`
- `frontend/src/features/accounts/AccountApp.test.tsx`
- `frontend/src/shared/i18n/ko.json`

## Validation

From `frontend/`:

- `npm test`: 300 tests passed in 29 files. Existing Settings tests now assert profile identity, email/empty-email states, administrator/member labels, empty roles, and absence of the test CSRF token while preserving administrator-only controls.
- `npm run build`: passed; the existing large-bundle warning remains.
- `npm audit --audit-level=moderate`: passed with zero vulnerabilities.
- `git diff --check`: passed.
- `cargo check --manifest-path src-tauri/Cargo.toml`: blocked by the existing stale Tauri permission-cache path pointing to `workflow-helper`. The clean-cache alternative passed:

```bash
CARGO_TARGET_DIR=/tmp/nexgent-language-cargo cargo check --offline --manifest-path src-tauri/Cargo.toml
```

## Remaining verification

The profile is read-only; account editing remains an administrator operation. No browser runtime was available, so authenticated visual verification remains outstanding. With the backend running, start:

```bash
npm run dev -- --host 127.0.0.1
```

Visit `http://127.0.0.1:5173/settings` as an administrator and a member. Check that the displayed identity belongs to the signed-in account, switch Korean/English, verify an account without email/roles, and resize below 640px with a long name/email to confirm wrapping.
