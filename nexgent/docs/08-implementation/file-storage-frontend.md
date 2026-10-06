# File Storage frontend and API integration

Date: 2026-09-30

The browser app now includes a **File Storage** sidebar entry at `/file-storage`.
It connects to the authenticated `/api/file-storage` backend service; file contents
continue to use `Nexgent/FileStorage` in Nextcloud and metadata stays in PostgreSQL.
The existing shared NextCloud page remains a separate section.

## Implemented interactions

- My files and Trash views, folders-first listings, 50-item pagination, breadcrumbs,
  and direct folder URLs at `/file-storage/folders/<UUID>`.
- `/file-storage/trash`, reloadable folder links, and browser Back/Forward support.
- Global filename search, empty/loading/error states, and manual refresh.
- Multi-file picker and drag/drop uploads into the current folder. The confirmation
  dialog lists files, supports removing individual selections and checks the API's
  file count, per-file and batch byte limits before upload. A folder picker and
  recursive folder drops preserve nested paths; dropped folders include empty directories. Uploads do not overwrite existing files.
- New folder, rename, move, recursive copy, original-file download, and a details
  dialog with size/type/timestamps/location and an Open containing folder action.
- Row actions and page-scoped multi-selection for move/copy/trash/restore/permanent
  deletion. Moving to trash and permanent deletion require an in-app confirmation.
- A paginated folder chooser prevents selecting a moved/copied folder or its
  descendants. Restore supports the original location or an explicitly chosen
  destination, with an optional name field; duplicate names are numbered automatically.
- Bulk operations run sequentially and stop at the first failure. The UI reports
  completed items, preserves the destination, and retries only remaining items.
  Batch uploads use the backend's atomic batch endpoint.
- Native modal dialogs with focus containment and Escape handling, labeled icon
  buttons and checkboxes, inline status/error feedback, and reduced-motion support.
- English and Korean copy, including errors and status messages. Filenames remain
  user content and are never translated. Narrow layouts hide secondary columns and
  retain file names, selection and actions.

Search is across all active files. Clear search to create a folder or upload into
the currently browsed directory. Multi-select applies to the displayed page and
clears when navigating or changing search/page. Downloads are offered for individual
files; there is no ZIP/folder download or bulk-download endpoint.

## Integration decisions

`src/shared/api/fileStorageClient.ts` owns HTTP calls and typed API data.
Components use the shared adapter and TanStack Query, with cache keys scoped to the
signed-in account ID. The existing `authenticatedFetch` attaches session cookies
and CSRF headers and triggers the app's sign-in flow on `401`. Requests remain
same-origin through the existing `/api` proxy; no Nextcloud credentials enter the UI.

Folder paths contain only entry UUIDs, not Nextcloud paths. The UI gets upload
limits from `/capabilities`, omits the multipart Content-Type header so the browser
sets its boundary, and preserves the difference between an omitted restore parent
(original location) and explicit null (root). Downloaded blobs use the backend's
UTF-8 Content-Disposition filename and object URLs that are revoked after use.

Mutations have no automatic retries. Listings are invalidated after successful or
failed mutations because a lost response can follow a committed upload. Navigation
away aborts in-flight browser requests; the server may already have completed the
operation, so returning to the page reloads the authoritative tree. There is no
resumable upload or progress percentage; busy state is indeterminate.

This follows the current authenticated browser architecture, which already uses
backend HTTP adapters. The frontend guide's original Rust-command direction does
not describe the current browser feature boundary. No OS/file-system access, Tauri
plugin, capability, CSP relaxation, or runtime dependency was added. Existing
AuthGate behavior still directs native Tauri users to the browser sign-in flow.

## Running and validation

Before using a deployed backend, apply the storage migration and use the cleanup
schedule described in [File Storage service](file-storage-service.md). With that
backend running, use the existing frontend proxy configuration:

```bash
cd frontend
NEXGENT_BACKEND_TARGET=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1
```

Open `/file-storage` after signing in. Production builds use the existing same-origin
proxy; no new host or route forwarding configuration is needed.

Validation on 2026-09-30:

- `npm run build`: passed (TypeScript and Vite). Vite still reports the application's
  existing large-chunk warning; no new dependency was introduced.
- `npm test`: 33 test files, **318 tests passed**.
- `CARGO_TARGET_DIR=/tmp/nexgent-storage-cargo cargo check --manifest-path src-tauri/Cargo.toml --offline`:
  passed. The default target cache contained stale paths from another workspace;
  a fresh temporary target resolved that environment issue without Rust changes.
- `npm audit --audit-level=moderate`: **0 vulnerabilities**.
- Saved Chromium browser regression: passed; desktop (1440px), narrow (760px),
  and Korean screenshots were inspected.
- `git diff --check` and Python compilation of the smoke fixture: passed.

The reusable browser regression uses **real authentication, CSRF checks and storage
HTTP endpoints**, a freshly migrated temporary SQLite database, and an in-memory
Nextcloud substitute. It covers create/rename, folder reload/history, multi-upload,
original-byte download with Unicode filename, move/copy, search/details, trash and
restore, bulk permanent deletion, conflict handling, partial-bulk retry, upload retry,
English/Korean layout, responsive width, and isolation for an ordinary second user.
It verifies a fixture marker before deleting any test entries.

To reproduce without modifying production dependencies, install browser tools under
`/tmp`, then run the backend and frontend in separate terminals:

```bash
npm install --prefix /tmp/nexgent-storage-browser --no-audit --no-fund @playwright/test
node /tmp/nexgent-storage-browser/node_modules/playwright/cli.js install chromium --only-shell

# Terminal 1, from backend/; uses temporary storage and test-only accounts.
uv run uvicorn tests.file_storage_smoke_server:app --host 127.0.0.1 --port 8769

# Terminal 2, from frontend/.
NEXGENT_BACKEND_TARGET=http://127.0.0.1:8769 npm run dev -- --host 127.0.0.1 --port 5187

# Terminal 3, from frontend/.
NODE_PATH=/tmp/nexgent-storage-browser/node_modules node tests/file-storage.browser.cjs
```

The fixture must stay bound to loopback. Its accounts are `alice` and `bob`, both
with the test-only password `test-pass`. Every backend startup creates a new
isolated database. Screenshots are written to `/tmp/file-storage-desktop.png`,
`/tmp/file-storage-narrow.png`, and `/tmp/file-storage-korean.png`.

No live Nextcloud files or deployed services were changed. Remaining live verification:
start the regular backend with its migration/configuration, open `/file-storage`,
upload a disposable file, download and compare its bytes, and check it with a second
login. Verify its physical object is under `/Nexgent/FileStorage`, then trash/purge
that test entry and run `uv run python -m app.file_storage.maintenance --limit 100`.

## File previews — 2026-09-30

File clicks and the Preview row action now open an integrated read-only viewer.
File details remain available from the viewer and row menu. Image/PDF/Markdown/text
and Office previews, original downloads, and retry/fallback behavior are described
in [File Storage previews](file-storage-previews.md), including updated validation.

## Automatic duplicate names — 2026-09-30

Same-name selections in one upload are accepted. The server assigns numbered
names and the refreshed list shows them. Upload, folder, destination and rename
dialogs explain that existing files are preserved. See
[Automatic duplicate names](file-storage-duplicate-names.md) for details.

## Folder uploads — 2026-09-30

Folder uploads are now supported through the picker and drag/drop, including
atomic metadata creation and duplicate-root numbering. See
[File Storage folder uploads](file-storage-folder-upload.md) for the API manifest,
browser behavior, limits and updated validation.

## Pre-PR validation — 2026-10-06

- `npm test`: 327 tests passed across 34 files.
- `npm run build`: passed, with the existing large-chunk warning.
- `CARGO_TARGET_DIR=/tmp/nexgent-storage-cargo cargo check --manifest-path src-tauri/Cargo.toml --offline`: passed.
- `npm audit --audit-level=moderate`: failed with one high vulnerability in
  `source-map-js` and four low findings involving KaTeX and its dependents.
  These findings supersede the September 30 clean audit; dependency manifests
  and lockfiles are unchanged in this PR. Dependency remediation remains follow-up work.
- Browser regressions and live Nextcloud checks were not rerun for this commit;
  use the reproduction commands and live verification steps above.
