# Nextcloud Nexgent Folder Scope

Date: 2026-09-30 (Asia/Seoul)

## Implementation

Changed the Nextcloud file browser root from `/Slack` to `/Nexgent`, matching
`https://nextor-ai-02.tail8e1643.ts.net/apps/files/files/784?dir=/Nexgent`.
This supersedes the folder selection in `nextcloud-slack-folder-scope.md`.

The backend `FILES_ROOT` constant scopes WebDAV listing, reads, previews,
downloads, and mutation source/destination paths to
`/remote.php/dav/files/<configured-user>/Nexgent/`. API paths remain relative
to this folder. Existing origin, account, traversal, and immediate-child listing
checks remain in place. The frontend root and nested breadcrumbs show `Nexgent`;
root navigation cannot go above this folder. The Files-app ID `784` is not a
WebDAV path component. Existing authentication and TLS configuration is retained.

## Validation

- Backend: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_nextcloud_client.py -q -p no:cacheprovider` from `backend/`: 24 passed, including exclusion of the previous Slack root.
- Frontend: `npm test -- src/features/nextcloud/NextcloudPage.test.tsx` from `frontend/`: 3 passed.
- Frontend: `npm run build`: passed with the existing large-bundle warning.
- Frontend: `CARGO_TARGET_DIR=/tmp/nexgent-language-cargo cargo check --offline --manifest-path src-tauri/Cargo.toml`: passed; sandbox stream-fd warnings were emitted.
- Frontend: `npm audit --audit-level=moderate`: zero vulnerabilities.
- `git diff --check`: passed.

## Operational verification and limitations

A read-only live `/Nexgent` WebDAV listing using `backend/dev.env` returned HTTP
401. Live folder contents and browser behavior could not be verified with these
credentials. The sandbox network probe stalled and was stopped; the 401 came
from a subsequent network-enabled probe. No deployment was restarted.

To apply to the selected deployment, run from `nexgent/`:

```bash
# Development
docker compose up -d --build backend frontend
# Or production
docker compose -f compose.prod.yaml up -d --build backend frontend
```

Verify the configured Nextcloud account/app password if the running application
also returns 401. After signing in, open `/nextcloud` and check the `Nexgent`
breadcrumb, immediate children, nested navigation, preview, and download.
An authenticated API check using an existing login cookie jar is:

```bash
curl --fail-with-body --cookie cookies.txt 'http://127.0.0.1:8000/api/nextcloud/files'
```
