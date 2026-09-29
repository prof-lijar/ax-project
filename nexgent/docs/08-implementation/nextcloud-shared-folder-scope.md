# Nextcloud Shared Folder Scope

Date: 2026-09-28 (Asia/Seoul)

## Implementation

The Nextcloud browser is now rooted at `/Shared`, corresponding to the user's Nextcloud link `https://nextor-ai-02.tail8e1643.ts.net/apps/files/files/690?dir=/Shared`. The Files-app URL and numeric file ID are UI navigation data; integration requests continue to use WebDAV with the existing server URL and service-account credentials.

`backend/app/nextcloud/client.py` mounts every relative file path below `/remote.php/dav/files/<configured-user>/Shared/`. The empty path lists `/Shared`; a client path such as `Reports/summary.pdf` addresses `/Shared/Reports/summary.pdf`. Returned file paths are relative to `/Shared`, preserving the existing browser navigation and API shapes. Subfolders can be browsed, but Back stops at the Shared root. The breadcrumb root now reads `Shared`, using the actual folder name in both languages.

The same URL builder scopes listing, text reads, previews, downloads, and existing file mutation/copy/move destinations. PROPFIND parsing ignores entries from other users, origins, sibling folders, traversal paths, and descendants outside the requested depth-one folder. Existing traversal rejection is retained. Automatic upstream redirects are disabled so a file request cannot silently leave the mounted location. If `/Shared` does not exist or the configured account cannot read it, the existing unavailable-files state is used; there is no account-root fallback.

No credentials, TLS verification settings, or server URL configuration were changed. The existing `NC_URL`, `NC_USER`, and `NC_PASS` must identify the intended Nextcloud instance and an account with access to `/Shared`. Reload/restart the backend to apply this change, and reload the UI to clear any previous account-root navigation state. This scopes the Nexgent Nextcloud integration; it does not alter Nextcloud's own permissions or the user's standalone Files app.

## Validation

From `frontend/`:

- `npm test`: 309 tests passed across 31 files. The toolbar assertion verifies the Shared root and absence of parent navigation there.
- `npm run build`: passed with the existing large-bundle warning.
- `npm audit --audit-level=moderate`: zero vulnerabilities.
- `git diff --check`: passed.
- `cargo check --manifest-path src-tauri/Cargo.toml`: encountered the existing stale Tauri permission-cache path referencing `workflow-helper`; the clean-cache command passed:

```bash
CARGO_TARGET_DIR=/tmp/nexgent-language-cargo cargo check --offline --manifest-path src-tauri/Cargo.toml
```

From `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_nextcloud_client.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
```

Nextcloud tests: 22 passed. Coverage includes the root URL, nested path encoding, outside-root href rejection, Unicode/space/percent-character round trips, sibling/descendant filtering, and scoped reads/previews/downloads/copy/move paths.

Full backend suite: 169 passed, 3 skipped (PostgreSQL-specific schema/locking checks). Existing FastAPI deprecation warnings remain.

The credential-free check `curl -sS -I --max-time 15 'https://nextor-ai-02.tail8e1643.ts.net/apps/files/files/690?dir=/Shared'` failed TLS hostname verification: the presented certificate identifies `192.168.0.18`, not the requested hostname. Certificate verification was not bypassed. Actual `/Shared` contents and access were therefore not verified.

## Remaining live verification

With the existing configured backend environment, run from `backend/`:

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

From `frontend/`:

```bash
npm run dev -- --host 127.0.0.1
```

After resolving the Nextcloud certificate/hostname mismatch if the configured connection also encounters it, sign in at `http://127.0.0.1:5173/nextcloud`. Confirm that the root lists only `/Shared` contents, open a nested folder, return to Shared, preview/download a file, and check Unicode names. A browser runtime and authenticated live Nextcloud verification were unavailable in this session.
