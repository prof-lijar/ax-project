# Password Reset Confirmation

Date: 2026-09-28 (Asia/Seoul)

## Implementation

The administrator password-reset form in Settings now requires a second password field, labeled Confirm password / 비밀번호 확인. Both fields use password masking, new-password autocomplete, and the existing required 4–12 character constraints.

Before any reset request, the form compares the two values exactly (without trimming) and invokes browser constraint validation. Mismatches show Passwords do not match / 비밀번호가 일치하지 않습니다 and prevent the request. Editing either field clears stale custom validation so the user can correct and resubmit. Matching values still must pass the native field constraints.

Passwords remain in uncontrolled form inputs and transient submission values; neither is put in React state or browser storage. Only the original password is passed to the existing reset API. The form clears before the valid request, disables its fields while busy, and uses the target user's ID as its React key so switching reset targets clears previous inputs. Existing logout-on-reset behavior remains unchanged. This change applies to password reset; the account-creation form is unchanged.

Files: `frontend/src/features/accounts/AccountApp.tsx`, `passwordConfirmation.ts`, `passwordConfirmation.test.ts`, and `frontend/src/shared/i18n/ko.json`.

## Validation

From `frontend/`:

- `npm test`: 304 tests passed across 30 files; confirmation coverage includes mismatches, Korean error copy, correction, exact character comparison, and honoring required-field validity.
- `npm run build`: passed with the existing bundle-size warning.
- `npm audit --audit-level=moderate`: passed, zero vulnerabilities.
- `git diff --check`: passed.
- `cargo check --manifest-path src-tauri/Cargo.toml`: encountered the existing stale Tauri permission-cache path referencing `workflow-helper`. The clean target check passed:

```bash
CARGO_TARGET_DIR=/tmp/nexgent-language-cargo cargo check --offline --manifest-path src-tauri/Cargo.toml
```

## Remaining browser verification

A browser runtime was unavailable, so native validation bubbles and authenticated reset requests were not exercised end to end. With the backend running, start:

```bash
npm run dev -- --host 127.0.0.1
```

Sign in as an administrator at `http://127.0.0.1:5173/settings`. Reset a test account: confirm mismatched or missing confirmation sends no request, correct either input and retry, and verify a matching valid password sends only the original password. Check Korean/English validation text, cancel/reopen, switching reset targets, and busy-state controls.
