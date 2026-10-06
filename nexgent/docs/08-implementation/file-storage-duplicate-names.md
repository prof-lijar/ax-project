# Automatic duplicate names in File Storage

Date: 2026-09-30

File Storage now keeps both items when a name already exists in the destination.
For example, repeated uploads of `file_name.pdf` create `file_name(1).pdf`,
`file_name(2).pdf`, and so on. Existing bytes and metadata are not overwritten.

## Behavior

- Applies to uploads (including duplicate names within one batch), new folders,
  copy, move, rename and restore. API responses contain the final assigned name.
- Checks active siblings for the same user, deployment and destination folder.
  Trashed names do not block reuse. Names remain NFC-normalized and case-sensitive.
- Inserts the lowest available positive number immediately before the final file
  extension. Extensionless files and dotfiles get the number at the end. Folder
  names are treated as a whole, including any dots.
- On collision, an existing numeric suffix is reused as a numbering family:
  `report(1).pdf` can become `report(2).pdf`, without nested `(1)(1)` suffixes.
- No-op renames/moves exclude the current entry. Unoccupied requested names are
  unchanged. Long names are truncated on UTF-8 character boundaries to remain
  within 255 bytes, preserving the extension where it fits; exceptionally long
  extensions are also shortened to leave room for numbering.
- The upload dialog accepts same-name selections and explains automatic numbering
  in English and Korean. Other destination/name dialogs show the same guidance.

## Storage and concurrency

`StorageStore.unique_name` resolves names inside the existing short owner-locked
PostgreSQL mutation transaction. Uploads reserve blob IDs, upload bytes to Nextcloud,
and allocate visible names only when publishing metadata. This handles names
created while remote upload was running and overlapping batches. Existing database
unique indexes remain the final invariant. Tree/cycle and ownership checks remain.
No schema migration or new dependency is required.

`GET /api/file-storage/capabilities` now reports
`name_conflict_policy: "auto_rename"`. Name collisions no longer produce a normal
409 response. Other invalid operations still can. Repeating a successful upload
creates another numbered item: uploads do not provide idempotency keys, and the UI
continues to avoid automatic mutation retries.

## Validation

- `.venv/bin/python -m pytest -q tests/test_file_storage.py`: **45 passed, 1 skipped**.
  Covers numbering, extension/Unicode handling, same-batch normalization, overlapping
  reservations, occupied suffixes, trash reuse, folder scope, move/rename/copy/restore,
  and original-byte preservation. The PostgreSQL-only row-lock test is skipped in
  this SQLite test environment; overlapping reservation/commit order is tested.
- Frontend `npm test`: **322 passed**. `npm run build`: passed, with the existing
  large-chunk warning. Required Rust check using `/tmp/nexgent-storage-cargo`: passed.
  `npm audit --audit-level=moderate`: zero vulnerabilities.
- Browser regression checks same-name files in one batch, a later duplicate upload,
  automatic folder numbering, and the existing file manager operations using real
  APIs with isolated SQLite and in-memory Nextcloud.

To reproduce the browser check, start the fixture and frontend described in
[File Storage frontend](file-storage-frontend.md), then run from `frontend/`:

```bash
NODE_PATH=/tmp/nexgent-storage-browser/node_modules node tests/file-storage.browser.cjs
```

No live Nextcloud or deployed service was changed. Remaining live verification:
upload the same disposable filename twice in the deployed File Storage UI, confirm
both numbered entries and original download bytes, and repeat with simultaneous
uploads against the PostgreSQL-backed deployment.
