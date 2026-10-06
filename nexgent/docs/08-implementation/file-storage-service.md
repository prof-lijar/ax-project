# Per-user file storage service

Date: 2026-09-30

The backend provides `/api/file-storage` for the File Storage sidebar page.
This document covers the service and APIs; see [File Storage frontend](file-storage-frontend.md)
for the implemented browser page and UI validation. PostgreSQL owns each user's
logical file/folder tree; Nextcloud stores immutable file contents.

## Architecture and ownership

Migration `20260930_06` adds `file_storage.storage_entries` and
`file_storage.storage_blobs`. Ownership always comes from the authenticated browser
session. The existing Origin and CSRF checks protect mutations. Other users' IDs
return `404`, including for administrators; there is no arbitrary-path or owner-ID
input. Composite foreign keys prevent cross-user and cross-deployment parent/blob
references. PostgreSQL locks the owner's account row during short metadata
transactions to serialize conflicting names, moves, copies and deletes across API
workers. Network requests never run while holding that lock.

The Nextcloud service account stores content at:

```text
Nexgent/FileStorage/<deployment>/<user UUID>/<blob UUID>
```

This is inside the requested `/Nexgent` directory, under the reserved `FileStorage`
subfolder. The shared browser hides this subfolder and rejects direct access to it
through every path-based file operation. Shared-root download, copy, move, delete
and replacement are also blocked so they cannot export or mutate private contents
indirectly. The service account must have write access to the existing `Nexgent`
directory. Do not share `FileStorage` through Nextcloud or modify its objects directly. Nextcloud administrators and the service account still have
physical access; the per-user boundary is enforced by Nexgent, not separate
Nextcloud accounts.

Folders exist only in PostgreSQL. Rename and move change metadata. Recursive copy
creates independent entries referencing the same immutable content; deleting one
copy does not remove content still referenced by another copy or trash item.
User-facing responses never expose blob paths, service credentials or owner IDs.

Uploads first validate bounded file contents and reserve blob IDs in PostgreSQL,
then PUT content to Nextcloud, then publish all entries in one transaction. A batch
is all-or-nothing in the logical tree. Upstream failures return a sanitized `502`.
Failed uploads leave durable cleanup records. A lost acknowledgement after a
successful database commit does not delete published content. Retrying a published
upload with the same name creates a numbered duplicate; upload requests do not have idempotency keys.

## API contract

Every endpoint requires the existing login cookie. Mutations additionally require
`Origin` matching `NEXGENT_PUBLIC_URL` and the current `X-CSRF-Token` from `/api/me`.
All IDs are UUIDs. `parent_id: null` represents the user's root.

| Method and path (prefix `/api/file-storage`) | Request / result |
| --- | --- |
| `GET /capabilities` | Upload limits, case-sensitive naming, conflict policy, trash support |
| `GET /entries` | Direct children; optional `parent_id`, `limit` (1–200, default 100), `offset` |
| `GET /entries?q=report` | Literal, case-insensitive name search across the user's active tree; ignores directory scoping, validates any supplied parent |
| `GET /entries/{id}` | Entry metadata plus ancestor `breadcrumbs`, ordered from root |
| `POST /folders` | JSON `{ "name": "Reports", "parent_id": null }`; returns entry, `201` |
| `POST /files` | Multipart repeated `files`, optional `parent_id` and folder `tree` manifest; returns `{ "items": [...] }`, `201` |
| `GET /entries/{id}/download` | Original bytes with the current logical filename; attachment, octet-stream, nosniff |
| `PATCH /entries/{id}` | JSON `{ "name": "New name.txt" }`; rename |
| `POST /entries/{id}/move` | JSON `{ "parent_id": null, "name": "optional new name" }` |
| `POST /entries/{id}/copy` | Same destination body; recursive copy, returns new root entry, `201` |
| `DELETE /entries/{id}` | Move entry/subtree to trash, `204` |
| `GET /trash` | Paginated independently trashed roots, same `limit`/`offset` parameters |
| `POST /trash/{id}/restore` | JSON `{}` preserves original parent/name; explicit `parent_id: null` restores to root; optional `name` resolves a conflict |
| `DELETE /trash/{id}` | Permanently delete metadata for a trash root and queue unreferenced contents for cleanup, `204` |

List responses contain `items`, `total`, `limit`, and `offset`, sorted folders first,
then case-insensitive name and stable ID. Entry fields are `id`, `parent_id`, `name`,
`kind` (`file` or `folder`), `size` (bytes; zero for folders, not recursive size),
`content_type`, `created_at`, `updated_at`, and `deleted_at`. Timestamps are UTC.
Content type is validated client-supplied metadata, not a verified file signature;
downloads always use `application/octet-stream`.

Names are NFC-normalized, trimmed, case-sensitive and limited to 255 UTF-8 bytes.
Empty names, dot/dot-dot, path separators and control characters are rejected.
Existing active sibling names are automatically numbered, such as `report(1).pdf`;
no operation silently overwrites data. Capabilities report `name_conflict_policy: "auto_rename"`.
Moving/copying a folder into itself or a descendant returns `409`. Operations on a
subtree exceeding 10,000 entries return `413`. Errors follow the existing envelope:

```json
{"error": {"code": "folder_cycle"}}
```

Trashing a folder hides all active descendants. Restore the trash root to recover
that group. Earlier independently trashed children remain separate trash items.
Purging their original parent preserves those items and changes their restore
parent to root. An unavailable restore parent returns `404`; provide a new parent
or explicit null. Trash has no automatic expiry.

Example, using an existing login cookie jar and CSRF token:

```bash
curl http://127.0.0.1:8000/api/file-storage/files \
  --cookie cookies.txt \
  --header 'Origin: http://localhost:5173' \
  --header 'X-CSRF-Token: YOUR_CSRF_TOKEN' \
  --form 'files=@report.pdf' \
  --form 'files=@notes.txt'
```

## Configuration and operation

Existing `NC_URL`, `NC_USER`, `NC_PASS`, TLS and timeout configuration is reused.
New optional variables are documented in `backend/example.env`:

| Variable | Default |
| --- | --- |
| `FILE_STORAGE_DEPLOYMENT` | Existing `AX_CHAT_DEPLOYMENT`, otherwise `default` |
| `FILE_STORAGE_MAX_FILE_BYTES` | 26214400 (25 MiB) |
| `FILE_STORAGE_MAX_BATCH_BYTES` | 104857600 (100 MiB) |
| `FILE_STORAGE_MAX_FILES` | 20 |

Deployment IDs accept 1–64 ASCII letters, digits, underscores or hyphens. Use a
stable, distinct ID per deployment sharing PostgreSQL or Nextcloud. Changing it
changes the visible namespace; it does not migrate existing data. API and cleanup
processes must use the same database, deployment and Nextcloud configuration.

From `backend/`, with the appropriate environment loaded:

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
uv run python -m app.file_storage.maintenance --limit 100
```

API startup checks that storage tables exist. Schedule the maintenance command
periodically (for example every five minutes) in the deployment's existing process
scheduler, with the same environment and working directory. Scheduling and deploying
it are operational follow-up; this change does not alter the running stack.

Maintenance retries pending deletions and expires abandoned upload reservations
after 24 hours. Missing remote blobs (`404`) count as successful deletion. Failed
remote deletion records remain for retry and produce a nonzero exit status. Its
JSON output reports `removed` and `failed`; increase `--limit` if the backlog exceeds
100 objects. Metadata deletion takes effect immediately; Nextcloud space is only
reclaimed after maintenance. Never delete ready blob records manually. Back up
PostgreSQL and the private Nextcloud root together. A schema downgrade removes
metadata but deliberately does not delete remote contents; retain backups before
any rollback.

## Validation and remaining checks

Automated tests cover migrated schema/model parity, owner/deployment isolation,
authentication and CSRF, bounded atomic uploads, sanitized upstream failures,
ambiguous commit cleanup, Unicode names, literal search, breadcrumbs, move/copy
cycles, trash/restore conflicts, reference-safe deletion, and stale-upload cleanup.
The existing shared Nextcloud client's root isolation is also regression-tested.

Validation on 2026-09-30:

- The final PostgreSQL storage and migration suite passed all 25 tests, including
  concurrent moves, schema/model parity and isolation from unrelated public tables.
- The complete SQLite-backed regression suite passed: 267 passed, 6 skipped
  (PostgreSQL-only checks). Existing FastAPI/Python deprecation warnings remain.
- `git diff --check` and Python compilation passed.

Commands (from `backend/`):

```bash
uv run pytest -q
NEXGENT_TEST_DATABASE_URL='postgresql+psycopg://USER@HOST/postgres' \
  uv run pytest -q tests/test_file_storage.py \
  tests/identity/test_accounts.py::test_final_schema_matches_models \
  tests/identity/test_accounts.py::test_fresh_auth_schema_ignores_public_user_table
```

The PostgreSQL test role must be allowed to create/drop disposable test databases.
Validation used an isolated PostgreSQL 18 cluster under `/tmp`, accessed only over
its private Unix socket; it did not use the deployment database.

Live Nextcloud upload/download was not exercised: tests use an in-memory fake or
mock transport, and no deployment data was changed. After migration in a staging
deployment, run the multipart curl above, list with
`curl --cookie cookies.txt http://127.0.0.1:8000/api/file-storage/entries`, download
an uploaded ID, and compare bytes. Test a second login to confirm isolation, then
trash/purge only the test entries and run the maintenance command above.

The service does not include public sharing, versioning,
in-place content replacement, resumable uploads, folder ZIP downloads, storage
quotas or automatic trash retention. Uploads buffer at most the configured batch
limit in application memory after multipart parsing; configure the reverse proxy's
request-body limit and timeouts to also bound incoming multipart traffic. SQLite
is used for local tests; production concurrency guarantees rely on PostgreSQL.

## Upload directory correction — 2026-09-30

The requested Nextcloud browser location is:

```text
https://nextor-ai-02.tail8e1643.ts.net/apps/files/files/784?dir=/Nexgent
```

Use `NC_URL=https://nextor-ai-02.tail8e1643.ts.net` (the server base URL, not the
browser URL). Uploads, downloads and cleanup all resolve to
`/remote.php/dav/files/<NC_USER>/Nexgent/FileStorage/<deployment>/<user UUID>/<blob UUID>`.
The database remains the authority for logical filenames and folders. The browser
file ID `784` is not used in WebDAV paths.

This supersedes the initial top-level `NexgentFileStorage/` physical location. No
live data was moved. If that initial implementation has already stored files, move
its contents into `Nexgent/FileStorage/` while the API and maintenance are stopped,
preserving deployment/user/blob paths, before switching to this version. No database
path migration is needed because blob paths are derived from those stable IDs.

The path correction includes regression tests for private WebDAV request URLs,
hiding reserved entries from shared listings, rejecting direct private operations
(including COPY/MOVE destinations), and blocking normalized shared-root operations.
Validation: `uv run pytest -q tests/test_nextcloud_client.py tests/test_file_storage.py tests/test_app.py` passed with 61 passed and 1 PostgreSQL-only test skipped. `git diff --check` passed. Live Nextcloud was not accessed.

## File previews — 2026-09-30

Authenticated previews are now available at `GET /entries/{id}/preview` under the
file-storage API prefix. See [File Storage previews](file-storage-previews.md) for
formats, Office conversion, response/error contracts, and validation.

## Automatic duplicate names — 2026-09-30

Uploads and folder operations now resolve duplicate names automatically. See
[Automatic duplicate names](file-storage-duplicate-names.md) for naming rules,
commit-time allocation, updated upload retry behavior, and validation.

## Folder uploads — 2026-09-30

The upload endpoint now accepts an optional relative-path tree manifest and can
create empty folders. All imported folders/files become visible in one transaction.
See [File Storage folder uploads](file-storage-folder-upload.md) for contracts,
validation limits, and browser/API tests.
