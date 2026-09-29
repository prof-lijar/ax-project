# Nextcloud Slack Folder Scope

Date: 2026-09-29 (Asia/Seoul)

## Implementation

Corrected the Nextcloud mount from `/Shared` to `/Slack`, matching the requested Files-app URL `https://nextor-ai-02.tail8e1643.ts.net/apps/files/files/690?dir=/Slack`. This supersedes the folder choice in `nextcloud-shared-folder-scope.md`; that historical record is retained.

The backend `FILES_ROOT` constant now scopes WebDAV listing, reads, previews, downloads and existing mutation destinations to `/remote.php/dav/files/<configured-user>/Slack/`. Returned paths remain relative to this folder. Origin, account, traversal and depth-one boundaries remain enforced. The frontend root breadcrumb reads `Slack`, with no parent navigation at the root. The browser URL's numeric file ID is not used as a WebDAV path. No authentication or TLS settings were changed.

## Validation

- Backend: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_nextcloud_client.py -q -p no:cacheprovider`: 23 passed. Existing boundary tests now exercise Slack; a regression case explicitly rejects Shared paths.
- Frontend: `npm test -- src/features/nextcloud/NextcloudPage.test.tsx`: 3 passed.
- `npm run build`: passed, with the existing large-bundle warning.
- `npm audit --audit-level=moderate`: zero vulnerabilities after rerunning with network access.
- `cargo check --manifest-path src-tauri/Cargo.toml`: failed due to the existing stale permission-cache path referencing workflow-helper. `CARGO_TARGET_DIR=/tmp/nexgent-language-cargo cargo check --offline --manifest-path src-tauri/Cargo.toml`: passed.
- `git diff --check`: passed before documentation was added; repeated at handoff.

## Operational verification and limitations

Read-only probes using both local backend env files returned HTTP 401 for capabilities and the previous Shared listing. The capabilities request does not depend on the folder root, so that authentication failure is separate from the incorrect folder scope. This does not establish what credentials the running containers use. Container inspection was unavailable: Docker socket access was denied and sudo required interactive authentication. No live Slack listing or authenticated browser check was completed, and no containers were restarted.

From the project root, apply the change to the selected deployment:

```bash
# Development (source mounts also support automatic reload)
docker compose up -d --build backend frontend
# Or production
docker compose -f compose.prod.yaml up -d --build backend frontend
```

Sign in and open `/nextcloud`; verify the Slack breadcrumb, only Slack children, nested-folder navigation, preview and download. If capabilities still returns 401, verify the running backend's Nextcloud account/app password and recreate that backend after correcting its env file. A folder change alone cannot fix capabilities authentication.
