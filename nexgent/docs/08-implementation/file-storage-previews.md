# File Storage previews

Date: 2026-09-30

Clicking a file in File Storage, or choosing **Preview** from its actions, now opens
an authenticated viewer. Back to files preserves the current folder/search. The
viewer includes file details, original-file download, loading feedback, retry for
transient errors, and English/Korean copy. Unsupported formats keep Download
available. Trashed files must be restored before viewing.

## Formats and rendering

| Files | Viewer |
| --- | --- |
| PNG, JPEG, GIF, WebP, BMP | Browser image |
| PDF | Browser PDF viewer with its native zoom/page controls |
| Markdown | Existing safe Markdown renderer |
| Text, CSV, JSON, XML, YAML, logs and supported source extensions | Escaped text |
| Word DOC/DOCX, Excel XLS/XLSX, PowerPoint PPT/PPTX, ODT/ODS/ODP, RTF | Read-only PDF converted by LibreOffice |

Office previews use LibreOffice Writer/Calc/Impress already included in the backend
Dockerfile. A non-container backend needs `libreoffice` or `soffice` on PATH. Each
conversion uses a temporary directory and separate LibreOffice profile, executes
off the async event loop, has a 60-second timeout, and removes temporary output.
Conversion never replaces the original Nextcloud object. Excel uses its PDF print
layout; interactive cells, editing, and collaboration are outside this viewer.
Rendering fidelity depends on installed fonts, document layout, and LibreOffice.
Encrypted, malformed, and unsupported files may not render.

## API and isolation

`GET /api/file-storage/entries/{entry_id}/preview` resolves the authenticated user's
active entry before reading its private Nextcloud object. The renderer receives
the database's logical filename and MIME type, since the stored blob has a UUID
name without an extension. The same renderer serves existing shared Nextcloud
previews. No additional Nextcloud sharing permissions or credentials enter the UI.

The response contains inline bytes, a UTF-8 Content-Disposition filename,
`X-Preview-Kind: image|pdf|text`, `nosniff`, and restrictive CSP. Existing middleware
adds `Cache-Control: no-store`. Missing, foreign, or trashed entries return 404;
folders cannot be previewed. Error codes are sanitized:

- 415 `preview_unsupported`
- 501 `preview_converter_unavailable`
- 504 `preview_timeout`
- 502 `preview_failed`

The frontend uses the shared authenticated API adapter, account-scoped query keys,
no background refetch/automatic retry, and revokes preview blob URLs when closing.
There is no database migration or dependency addition for this feature. Previews
buffer content in memory; Office conversion runs on demand without persistent
caching. The existing upload limits continue to bound stored file sizes.

## Validation and reproduction

- Backend full suite: **288 passed, 6 skipped**. Focused storage/Nextcloud suite:
  **68 passed, 1 skipped**. Includes owner isolation, trash denial, logical names,
  response types, Office conversion dispatch, safe errors, and unchanged downloads.
- Frontend: **322 tests passed**; TypeScript/Vite build passed with the existing
  large-chunk warning. Rust check passed using `CARGO_TARGET_DIR=/tmp/nexgent-storage-cargo`.
- `npm audit --audit-level=moderate`: zero vulnerabilities.
- Browser regression uses real authentication and storage APIs with temporary
  SQLite and an in-memory Nextcloud substitute. Genuine PNG/PDF/DOCX/XLSX fixture
  files exercise local LibreOffice conversion. It checks Markdown, images, PDF
  bytes/viewer, original Excel download, narrow layout, error/retry, and details.
- The existing full file-manager browser regression also passes after updating
  its file-click expectation to open the viewer before Details.

Start the isolated servers as documented in
[File Storage frontend](file-storage-frontend.md), then run from `frontend/`:

```bash
# Full Chromium is needed for its native PDF viewer (headless-shell lacks it).
node /tmp/nexgent-storage-browser/node_modules/playwright/cli.js install chromium --no-shell
NODE_PATH=/tmp/nexgent-storage-browser/node_modules node tests/file-storage-preview.browser.cjs
NODE_PATH=/tmp/nexgent-storage-browser/node_modules node tests/file-storage.browser.cjs
```

Screenshots: `/tmp/file-storage-preview-image.png` and
`/tmp/file-storage-preview-excel.png`. The Excel screenshot was visually inspected
with its converted content visible in Chromium's native PDF viewer.

No deployed service or live Nextcloud file was changed. Remaining live check:
start the regular backend/frontend with existing storage configuration, sign in,
upload disposable image/PDF/MD/DOCX/XLSX files, open each preview, download and
compare originals, and confirm a second account cannot access those entry IDs.
