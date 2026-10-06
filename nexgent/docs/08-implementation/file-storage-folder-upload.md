# File Storage folder uploads

Date: 2026-09-30

File Storage now accepts folders through **Upload folder** and drag/drop. The
selected top-level folder and its nested structure are recreated in the current
logical directory. Files still use private UUID objects in Nextcloud; PostgreSQL
owns their visible paths. The former folder-upload rejection was removed.

## User flow

The folder picker uses browser-provided relative paths. Drag/drop snapshots browser
entries during the drop event, recursively drains all directory-reader batches,
and includes empty directories. Multiple dropped files/folders share one upload.
The confirmation dialog shows relative file paths, included folders, sizes and
limits. Individual files can be removed before submission. Failed submissions
retain the selection for retry. Folder reading reports a busy state and is bounded
by the advertised count/byte/depth limits. Navigation/unmount prevents a completed
read from opening a dialog in another folder.

Existing destination folders are never merged or overwritten: uploading `Project`
again creates `Project(1)` and attaches all imported descendants to that new root.
The existing automatic numbering policy handles file collisions as well. Preview,
download, move/copy and trash behavior works on the imported entries normally.

Browser folder pickers expose files rather than empty directory entries, so empty
folders are preserved through drag/drop. A completely empty picker result gives
instructions to drag the folder instead. Folder entry reading depends on browser
support for `webkitGetAsEntry`; the file-only drop fallback remains available.
No native Tauri capabilities, OS access, or frontend runtime dependencies were added.

## API and atomicity

`POST /api/file-storage/files` retains its existing multipart contract and adds an
optional `tree` JSON form field:

```json
{"paths":["Project/notes.md","Project/Sub/data.txt"],"directories":["Project/Empty"]}
```

`paths` correspond to multipart `files` in order. Missing ancestor folders are
inferred; `directories` includes explicit folders, including empty ones. Empty-tree
uploads may omit `files` entirely when directories are present. Responses contain
`items` for created folders followed by files. Plain-file uploads keep their
existing response shape and behavior.

Paths must be relative slash-separated segments. Each segment is validated and
NFC-normalized under the existing filename rules. Absolute paths, dot/dot-dot,
empty segments, backslashes, control characters, file/folder overlap and mismatched
file/path counts return `422 invalid_upload_tree` before Nextcloud I/O. Limits are
32 path segments, 1,000 inferred/explicit folders and a 256 KiB manifest. Capabilities
advertise `folder_upload`, `max_upload_depth`, and `max_upload_folders`.

Existing `FILE_STORAGE_MAX_FILES`, `FILE_STORAGE_MAX_FILE_BYTES`, and
`FILE_STORAGE_MAX_BATCH_BYTES` apply to the whole upload (defaults: 20 files,
25 MiB each, 100 MiB total). Oversized folders must be split or these server limits
adjusted. The frontend shows the configured limits before submission. There is no
automatic batch splitting, resumable upload or percentage progress in this change.

The service validates the manifest, reserves blob IDs, uploads immutable content,
then creates all directories and file entries in one owner-locked transaction.
Failures publish no partial logical tree; uploaded-but-unpublished blobs use the
existing durable cleanup path. Empty-folder-only requests require no Nextcloud
content operations. Ownership, authentication, CSRF, and unique-name constraints
remain enforced. No new database migration is needed.

## Validation

- Storage API suite: **65 passed, 1 skipped**. Covers nested/empty folders, Unicode,
  duplicate roots, preserved original bytes and previews, unsafe paths, manifest
  bounds, ownership, upstream failure cleanup and transaction rollback. PostgreSQL
  row-lock test remains skipped in the local SQLite environment.
- Frontend suite: **327 passed**. TypeScript/Vite build passed with the existing
  large-chunk warning. Required Rust check passed with the temporary target cache;
  dependency audit reports zero vulnerabilities.
- Browser regression uses the real directory picker and Chromium native directory
  drag/drop, real auth/CSRF/storage APIs, temporary SQLite and an in-memory Nextcloud
  substitute. It covers nested Korean filenames, duplicate roots, previews, original
  download, empty directory uploads, retry, and narrow Korean UI.

With the isolated backend on 8769 and frontend on 5187 as described in
[File Storage frontend](file-storage-frontend.md), run from `frontend/`:

```bash
NODE_PATH=/tmp/nexgent-storage-browser/node_modules node tests/file-storage-folder-upload.browser.cjs
NODE_PATH=/tmp/nexgent-storage-browser/node_modules node tests/file-storage.browser.cjs
```

The folder regression creates temporary local input files and removes them after
execution. It checks the fixture marker before cleaning its own named test entries.
Screenshot: `/tmp/file-storage-folder-upload.png`.

No deployed service or live Nextcloud content was changed. Remaining live check:
upload a disposable nested folder through the regular File Storage page, upload it
again to check numbering, drag a folder containing an empty subfolder, and compare
downloaded bytes. Use a second account to verify that these entries remain private.
