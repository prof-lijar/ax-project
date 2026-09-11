# RAG Knowledge Search Workspace

Date: 2026-09-11

## Scope and design

Replaces the RAG route's Add/Search tabs with a persistent Knowledge search
workspace. This supersedes the two-tab layout described in
`rag-knowledge-workspace-refinement.md`; that historical record is unchanged.
The RAG concept, sidebar route, shared query hooks, API endpoints, request and
response contracts, defaults and service behavior remain unchanged.

The design was researched and planned before implementation:

- [NN/g progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/): keep advanced settings and technical metadata behind named disclosures.
- [Google source workflow](https://support.google.com/gemininotebook/answer/16215270): present imported files and pasted text as recognizable sources.
- [W3C modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/): contain keyboard focus, label dialogs and restore focus on dismissal.

Search-first prioritization is a design assumption rather than a result of user
analytics or usability studies. An empty knowledge collection emphasizes adding
the first source.

## Implementation

- Search remains visible with its submitted-query label. Result count is in a
  collapsed Search options disclosure, retaining default 5 and range 1–20.
- Ranked passage rows show source identity and excerpts in server order. The
  selected passage appears in an adjacent scrollable reading pane, with full
  text and paragraph breaks. Source details expose raw cosine similarity,
  document ID, passage index, token count and character offsets. Missing
  provenance is labeled unavailable; similarity is never called confidence.
- At viewport widths of 900px and below, selecting a passage replaces the list
  with its reader. Back to results restores focus to the selected row.
- Add source opens a modal right-hand drawer for file upload or pasted text.
  File, text and title drafts live in the page and survive dismissal. Chunk
  settings retain default 500 and range 100–1000. Pending operations prevent
  dismissal; failure retains input; success retains metrics and chunk previews.
- The drawer contains keyboard focus including textareas and disclosure
  summaries, excludes hidden controls, and restores focus after dismissal.
  The successful-source search action focuses the search field.
- Manage toggles counts and the existing clear-all operation. Exact DELETE,
  explicit final button activation, mutual operation guards and failure/retry
  behavior remain. Deletion refreshes counts and clears stale search results.
- CSS modules use existing design tokens and Lucide icons. Obsolete tab/card
  styles were removed. No dependencies, credentials, CSP or Tauri permissions
  changed.

Primary files: `frontend/src/features/rag/RagPage.tsx`,
`RagPage.module.css`, `RagDialog.tsx`, `RagPage.test.tsx`, and
`frontend/scripts/rag-ui-smoke.mjs`.

The API has no document-list, individual-delete, download or document-scoped
search operation. This interface does not simulate those capabilities. The
reader displays returned passages, not full original documents or generated
answers. Drafts are transient and do not survive page reloads.

## Validation

Run from `frontend/`:

- `npm test`: passed, 23 files / 250 tests. Removed the obsolete tab test;
  adapted rank/provenance assertions to the result list and selected reader.
- `npm run build`: passed. Vite retains a main-chunk size warning above 500 kB.
- `cargo check --manifest-path src-tauri/Cargo.toml`: the default target cache
  fails because it references a missing historical `workflow-helper` permission
  file. `CARGO_TARGET_DIR=/tmp/nexgent-chat-ux-cargo cargo check --offline --manifest-path src-tauri/Cargo.toml`
  passed using the existing isolated cache.
- `npm audit --audit-level=moderate --cache /tmp/nexgent-chat-npm-cache`:
  unavailable because registry DNS resolution failed (EAI_AGAIN). No current
  security-audit result is claimed.
- The mocked Chromium smoke script passed at 1440, 1024 and 760px without
  horizontal overflow or browser runtime errors. Checks include source drawer
  dismissal/focus, preserved text drafts, collapsed-control focus exclusion,
  pending controls, unsupported files, multiple-file rejection, file removal,
  text payload fields, chunk validation and previews, selected passages,
  narrow reader navigation, search validation and submitted-query labels,
  no matches, legacy provenance, indexing failure, and exact deletion
  confirmation with failure/retry, pending Escape and empty-state behavior.
- Desktop search, upload drawer and narrow reader screenshots were visually
  inspected in `/tmp/nexgent-rag-ui-artifacts` (temporary, not committed).

Reproduce browser verification with the already installed external Playwright:

```bash
npm run dev -- --host 127.0.0.1 --port 5187
```

In a second terminal, from `frontend/`:

```bash
PLAYWRIGHT_BROWSERS_PATH=/tmp/nexgent-chat-ui-tools/browsers PLAYWRIGHT_MODULE=/tmp/nexgent-chat-ui-tools/node_modules/playwright/index.mjs node scripts/rag-ui-smoke.mjs
```

All RAG requests, including writes and deletions, are intercepted by this script.
The tooling is outside project dependencies; setup instructions are in the
previous refinement document. `RAG_UI_URL` and `RAG_UI_ARTIFACTS` override the
preview URL and screenshot directory.

## Remaining verification

Live service ingestion/search and packaged Tauri interactions were not tested;
browser checks deliberately used intercepted requests. On a graphical host
with configured services, run `npm run tauri:dev` and exercise file selection,
source ingestion and search. For browser service verification run
`npm run dev -- --host 127.0.0.1` and open `/rag`. Rerun
`npm audit --audit-level=moderate` when registry access is available. The
historical Cargo cache issue and bundle-size warning remain follow-up work.

## Update: Visible passage limit

Date: 2026-09-11

Replaced the collapsed Search options disclosure with an always-visible
Passage limit number field between the query and Search button. Its range
(1–20), default (5) and validation remain unchanged. On widths at or below
560px the query takes its own row, followed by the limit and Search button.
This supersedes the collapsed result-count design described above.

Validation: all 250 tests, production build and the isolated-cache Cargo check
passed using the commands above. The mocked browser smoke check passed at
1440, 1024 and 760px, including an explicit assertion that Passage limit is
visible without interaction. The desktop screenshot was visually reviewed.
The npm audit retry remained blocked by registry DNS (EAI_AGAIN); the existing
bundle warning and live-service verification limitations still apply.
