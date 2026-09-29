# Administrator-Only Knowledge and Agent Pages

Date: 2026-09-28 (Asia/Seoul)

## Access policy

The Knowledge (`/rag`) page and every agent detail/workspace route (`/agents/:id`) now require an administrator account. This includes the generic detail page, Scout research/scheduling, and Weekly Reporter. The `/agents` catalog, Chat (including its existing RAG conversation option), files, and account settings remain available to authenticated members. The legacy `/test-agent` route resolves to the protected Weekly Reporter workspace.

The existing server definition of administrator is the `access.manage` permission, exposed through `/api/me` as `is_admin`. The implementation uses that existing definition rather than checking role names or introducing another permission system.

## Interface

- `AdminOnly` guards restricted route children before they mount. Members visiting a bookmarked URL see Access restricted / 접근 권한이 없습니다 and a localized administrator-only explanation with a button to return to Chat. Restricted page hooks and operations are not mounted.
- Knowledge remains visible as a disabled sidebar button with an administrator-only label. It has no navigation URL.
- Members can browse agent cards and use eligible Chat actions. Agent names have no detail link; Details, View details, and Open workspace controls are disabled. A catalog message explains the restriction.
- The view defaults to denied detail access unless the authenticated page passes `is_admin`. Existing query-driven account updates update guards and controls. Server authorization is checked on every request even before a browser account refresh.
- Korean and English labels use the shared translation catalog.

## Server enforcement

`backend/app/integrations.py` applies the existing `require_admin` dependency to all supported methods (GET, HEAD, POST, PUT, PATCH, DELETE) under:

- `/rag-api/`
- `/scout-api/`
- `/scout-scheduler-api/`
- `/weekly-report-bulk-api/`

Unauthorized members receive HTTP 403 with `permission_denied` before an upstream connection is opened. Sign-in and CSRF checks remain in place. `/agent-server/` and the existing Chat endpoints retain authenticated-member access. No database migration, capability, or dependency changes were needed.

These checks apply to the Nexgent gateway. Standalone upstream services must remain behind their existing network/authentication boundaries; this change does not reconfigure those separate services. Apply the backend code along with the frontend code for server enforcement; restart/reload the running backend as appropriate. For local development with the existing configured environment, run from `backend/`:

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Validation

From `frontend/`:

- `npm test`: 309 tests passed across 31 files. Access tests cover denied child mounting, admin access and subsequent role loss, Korean denial copy, disabled navigation, member card controls, and retained Chat access.
- `npm run build`: passed with the existing bundle-size warning.
- `npm audit --audit-level=moderate`: zero vulnerabilities.
- `git diff --check`: passed.
- Standard `cargo check --manifest-path src-tauri/Cargo.toml` encountered the existing stale Tauri permission path referencing `workflow-helper`. The clean-cache check passed:

```bash
CARGO_TARGET_DIR=/tmp/nexgent-language-cargo cargo check --offline --manifest-path src-tauri/Cargo.toml
```

From `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_integrations.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
```

Gateway tests: 60 passed, including administrator/member checks across all four restricted prefixes and all six methods, no upstream calls for members, retained member Chat gateway access, and revocation on the next request. FastAPI emits Python 3.14 deprecation warnings. The sandbox prevented the event-loop socket initialization used by TestClient; tests ran successfully with permitted local socket access.

Full backend suite: 159 passed, 3 skipped.

## Remaining browser verification

A browser runtime was unavailable. Start the UI from `frontend/` with `npm run dev -- --host 127.0.0.1`, sign in as a member, and verify disabled navigation/card controls and direct visits to `/rag`, `/agents/1`, `/agents/ansimk_scout_agent`, and `/agents/7`. Repeat as an administrator and check that each page operates normally. Verify both languages, retained member Chat access, and a role change while a protected page is open. Live deployment of the backend and authenticated end-to-end browser behavior were not performed in this session.
