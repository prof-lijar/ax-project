# Document Viewer

Date: 2026-07-03

## Summary

The NextCloud Drive view now supports view-only previews for common work files:

- PDF
- Markdown (`.md`, `.markdown`)
- Text (`.txt` and other text-like files)
- Images (`png`, `jpg`, `jpeg`, `gif`, `webp`, `bmp`)
- Office documents converted to PDF (`docx`, `pptx`, `xlsx`)

The viewer is part of the main NextCloud workspace. It does not restore the old right-side details panel.

## How It Works

- Frontend file rows show `View` for supported formats and `Download` for all files.
- `View` opens a full-workspace viewer with `Back` and `Download`.
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
