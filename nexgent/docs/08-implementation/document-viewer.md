# Document Viewer

Date: 2026-07-03

## Update: NextCloud File Workspace Polish

Date: 2026-08-14

The connected NextCloud workspace now has a compact page heading and explicit
current-location treatment. The root is labeled `All files`; nested folders
retain the existing parent action and clickable path segments, with an added
root jump. Folder navigation still uses page-local path state and the existing
path-keyed TanStack Query.

List mode now presents consistent Name, Type, Modified, and Size columns using
metadata already returned by the file-list operation. Concise labels are
derived from existing content types and filename extensions. Folders retain a
quiet folder-specific surface and omit irrelevant size detail. Card mode keeps
the existing open/download behavior while presenting the same metadata in a
compact wrapped line.

The List/Card control was refined as a compact segmented control with clearer
active, hover, focus-visible, and keyboard states. Responsive rules
progressively hide the Type, Modified, and Size columns, expose a compact
secondary line where useful, and collapse the card grid without horizontal
overflow. Breadcrumbs remain available through a narrow scrollable row.

No NextCloud operation was added or changed. Folder listing, preview, download,
retry states, viewer rendering, view-mode state, and preview object-URL cleanup
continue to use the existing frontend code. Upload, folder creation, rename,
move, delete, copy, and search remain absent from the UI. Shared APIs, Tauri
commands, backend routes, Chat, Agents, routing, and Zustand were not modified.

Validation completed from `frontend/`:

```bash
npm test -- src/features/nextcloud/NextcloudPage.test.tsx
npm run build
npm test
CARGO_TARGET_DIR=/tmp/nexgent-cargo-check.AytMsV cargo check --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
```

The focused suite passed all 3 tests, covering the root heading, nested
breadcrumbs, layout selection markup, folder-first sorting, and derived file
metadata. The full frontend suite passed all 37 tests. The TypeScript/Vite
production build and Cargo check passed, and the dependency audit reported zero
vulnerabilities. A connected NextCloud was not available for automated visual
interaction, so the remaining check is:

```bash
npm run dev -- --host 127.0.0.1
```

Open NextCloud at the root and in nested folders, switch between List and Card,
resize below 1050 px, 820 px, and 680 px, then confirm folder opening, file
preview, Download, breadcrumb navigation, and viewer Back behavior remain
unchanged.

## Summary

The NextCloud Drive view now supports view-only previews for common work files:

- PDF
- Markdown (`.md`, `.markdown`)
- Text (`.txt` and other text-like files)
- Images (`png`, `jpg`, `jpeg`, `gif`, `webp`, `bmp`)
- Office documents converted to PDF (`docx`, `pptx`, `xlsx`)

The viewer is part of the main NextCloud workspace. It does not restore the old right-side details panel.

## Update: One-click File Opening

Date: 2026-08-03

Previewable files now open when the user clicks the file content in the Drive
list. The separate `View` button was removed. Each non-folder file row now has
a vertical-ellipsis action button that opens a menu containing `Download`.

The file content and action menu are separate interactive controls. This keeps
the whole file-content area available as the primary open action while ensuring
that opening the menu or downloading does not also launch the viewer. The menu
supports keyboard focus, closes with Escape, and closes when the user clicks
outside it. Files without a supported preview remain non-clickable but retain
the Download menu.

Validation performed:

```bash
cd frontend
npm run build
CARGO_TARGET_DIR=/tmp/nexgent-cargo-check cargo check --manifest-path src-tauri/Cargo.toml
```

Both commands passed. An interactive check against a connected NextCloud was
not available in this environment. Remaining verification:

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

Open NextCloud, click a supported file once to confirm it enters the viewer,
then open the vertical-ellipsis menu and confirm Download runs without opening
the file. `npm audit --audit-level=moderate` also remains to be run in an
environment with approved npm registry access.

## Update: Compact Drive Toolbar

Date: 2026-08-03

The redundant `Drive`, `NextCloud`, and descriptive heading text was removed
from the selected NextCloud page. The visible `Files` root breadcrumb label and
root folder icon were also removed. No breadcrumb control is shown at the root;
inside a folder, a back arrow and actual folder names remain visible so users
can navigate the current path. The Refresh control remains available in the
compact toolbar.

`npm run build` passed after this change. Live folder navigation still requires
a connected NextCloud instance; run `npm run dev -- --host 127.0.0.1`, select
NextCloud, navigate into a folder, and verify that the back control and named
path segments navigate correctly.

## Update: List and Card Layouts

Date: 2026-08-03

The NextCloud file toolbar now provides icon-only List and Card controls in
place of the manual Refresh button. List is the default and retains the compact
file rows. Card mode displays both folders and files in a responsive grid with
larger file-type icons. The active layout remains selected while the user
navigates between folders.

Folder cards still open their folder with one click. Previewable file cards
still open the viewer with one click, and file downloads remain in the
vertical-ellipsis action menu. The switch uses labeled buttons and
`aria-pressed` so its current state is available to assistive technology.

`npm run build` and
`CARGO_TARGET_DIR=/tmp/nexgent-cargo-check cargo check --manifest-path src-tauri/Cargo.toml`
passed. Live visual verification still requires a connected NextCloud instance:
run `npm run dev -- --host 127.0.0.1`, select NextCloud, switch between both
layout icons, and verify folder navigation, file preview, and Download in each
layout.

The selected layout is currently page-local UI state and returns to List after
the NextCloud page is unmounted.

The file-list wrapper has no outer border or padding. Borders remain on the
individual folder and file items, avoiding a doubled container edge in both
List and Card layouts.

## How It Works

- Clicking a supported file opens a full-workspace viewer with `Back` and `Download`.
- The file-row vertical-ellipsis menu provides `Download` for all non-folder files.
- Browser preview calls the backend directly.
- Tauri preview calls a Rust command, which calls the same backend endpoint.
- The backend endpoint is:

```text
GET /api/nextcloud/files/preview?path=<nextcloud-path>
```

Response headers:

```text
Content-Type: application/pdf | image/* | text/*
X-Preview-Kind: pdf | image | text
Content-Disposition: inline; filename="fallback"; filename*=UTF-8''...
```

Unicode filenames are supported through `filename*`.

## Office Conversion Requirement

DOCX, PPTX, and XLSX are converted to PDF by LibreOffice in headless mode.

Install on the backend machine:

```bash
sudo apt update
sudo apt install libreoffice libreoffice-writer libreoffice-impress libreoffice-calc fonts-dejavu fonts-liberation fonts-noto fonts-noto-cjk
```

Verify:

```bash
which libreoffice
which soffice
libreoffice --headless --version
```

Restart the backend after installing:

```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Security Notes

- Markdown is rendered with React nodes, not raw HTML injection.
- Supported Markdown HTML is intentionally limited to safe `<details><summary>...</summary></details>` blocks.
- Links are limited to `http:`, `https:`, and `mailto:`.
- Other HTML is displayed as text.
- Preview files are served through the local backend; NextCloud credentials are never exposed to the frontend.
- Tauri CSP allows `blob:` only where needed for PDF/image rendering.
- NextCloud paths continue to use backend path normalization to reject traversal.

## Validation

Run:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev pytest
```

```bash
cd frontend
npm run build
cargo check --manifest-path src-tauri/Cargo.toml
```

Useful live checks:

```bash
curl -i "http://127.0.0.1:8000/api/nextcloud/files/preview?path=Readme.md"
curl -I "http://127.0.0.1:8000/api/nextcloud/files/preview?path=Reasons%20to%20use%20Nextcloud.pdf"
```

For LAN browser preview, confirm CORS exposes preview headers:

```bash
curl -I \
  -H "Origin: http://192.168.0.18:5174" \
  "http://127.0.0.1:8000/api/nextcloud/files/preview?path=Readme.md"
```

Expected exposed headers:

```text
Access-Control-Expose-Headers: Content-Disposition, X-Preview-Kind
```

## Known Limits

- Office previews are only as accurate as LibreOffice conversion and available fonts.
- XLSX preview is PDF-based, not an interactive spreadsheet.
- Large files may take time to preview because the current backend returns complete preview bytes.
- Preview is scoped to NextCloud Drive files only.
