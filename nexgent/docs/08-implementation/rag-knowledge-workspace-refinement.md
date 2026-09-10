# RAG Knowledge Workspace Refinement

Date: 2026-09-10

## Implemented

The RAG route now presents a Knowledge workspace with two clear actions: Add
knowledge and Search knowledge. The sidebar route remains RAG. A compact count
summary stays visible in either view, with retry when counts are unavailable.

Upload supports a single-file drop zone, filename/size preview, replacement and
removal. Paste text retains its optional title. Indexing options are collapsed
by default; validation, progress, failure messages, and the successful-source
summary remain next to the operation. Processing details retain chunk previews
and service metrics. A successful upload offers a direct move to search.

Search emphasizes ranked source names and passages. Long passages can be
expanded. Match details retain raw cosine similarity and source provenance;
scores are not presented as confidence. Result labels use the submitted query,
so editing the next query does not mislabel existing results. Empty, pending,
and failed states explain what happened.

Manage knowledge contains the existing database controls behind a disclosure.
Deletion still requires exact DELETE confirmation and an explicit button click.
The confirmation dialog is portaled outside the inert application root, focuses
its confirmation field, traps Tab navigation, restores focus after cancellation,
and allows Escape only while idle. Failed deletion stays visible in the dialog.
Deletion cannot begin while indexing/searching is pending.

## Architecture and preserved behavior

Only frontend presentation and interaction code changed. Components continue to
use the shared query/API adapter. No service endpoints, request schemas, model
settings, database behavior, dependencies, or Tauri permissions were changed.
File types remain TXT, MD, DOCX and PDF. Chunk tokens retain the 100–1000 range
and 500 default; search retains the 1–20 result range and 5 default. OCR copy
retains the existing service capabilities. This is passage retrieval, not a new
answer-generation or document-management API.

Primary implementation: `src/features/rag/RagPage.tsx`, its CSS module, and
`RagDialog.tsx`. Keyboard tabs use roving focus and arrow/Home/End navigation.
Styling follows existing tokens and supports narrow desktop layouts.

## Validation

Run from `frontend/`:

- `npm test`: passed, 23 files / 251 tests.
- `npm run build`: passed; existing size-warning category remains, with the main
  JavaScript chunk at approximately 510 kB (above Vite's 500 kB warning threshold).
- `cargo check --manifest-path src-tauri/Cargo.toml`: blocked by an existing
  default-target cache referring to a missing historical `workflow-helper`
  `app_hide.toml` path. The isolated-target check passed:
  `CARGO_TARGET_DIR=/tmp/nexgent-chat-ux-cargo cargo check --offline --manifest-path src-tauri/Cargo.toml`.
- `npm audit --audit-level=moderate --cache /tmp/nexgent-chat-npm-cache`: reported
  two existing moderate findings in Vitest/@vitest/mocker, GHSA-82fw-gwwq-j7x9.
  Dependency remediation is separate from this UI change.
- `scripts/rag-ui-smoke.mjs`: passed in Chromium with every RAG request mocked,
  including writes/deletion. Covered tab navigation, counts, search validation,
  submitted-query labels, expanded passages, unsupported files, file removal,
  multiple-file rejection, text indexing validation, pending controls, failed
  indexing, exact deletion confirmation, Escape/focus restoration, pending
  deletion, failure/retry and success. Layouts checked at 1440, 1024 and 760 px;
  screenshots were visually reviewed. No browser runtime errors were observed.

Reproduce the optional browser checks (Playwright is outside project dependencies):

```bash
npm install --prefix /tmp/nexgent-chat-ui-tools --no-package-lock playwright@1.63.0
PLAYWRIGHT_BROWSERS_PATH=/tmp/nexgent-chat-ui-tools/browsers node /tmp/nexgent-chat-ui-tools/node_modules/playwright/cli.js install chromium
npm run dev -- --host 127.0.0.1 --port 5187
```

In another terminal:

```bash
PLAYWRIGHT_BROWSERS_PATH=/tmp/nexgent-chat-ui-tools/browsers PLAYWRIGHT_MODULE=/tmp/nexgent-chat-ui-tools/node_modules/playwright/index.mjs node scripts/rag-ui-smoke.mjs
```

`RAG_UI_URL` overrides the preview URL; `RAG_UI_ARTIFACTS` overrides the screenshot
folder (default `/tmp/nexgent-rag-ui-artifacts`). Mock response delays allow
pending-state assertions to observe rendered state before completion.

## Remaining verification

Live indexing/search and the packaged Tauri webview were not exercised; browser
validation used mocked responses to avoid changing real knowledge data. Run
`npm run dev -- --host 127.0.0.1` with configured services for live checks, and
`npm run tauri:dev` on a graphical host for webview keyboard, file selection and
layout verification. The Cargo cache issue, audit findings and bundle warning
remain follow-up work.
