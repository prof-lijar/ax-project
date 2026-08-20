# RAG UI Integration

Date: 2026-08-20

## Purpose

This running implementation record covers the Nexgent frontend surface for the
existing RAG HTTP APIs. Server implementation history remains in
`RAG/docs/rag-server.md`; retrieval evaluation history remains in
`RAG/docs/rag-retrieval-evaluation.md`.

## Scope

The first UI integration targets host-run Vite browser development only:

- add `RAG` to the left navigation immediately before Settings;
- add a `/rag` page with Embedding and Search tabs;
- upload one UTF-8 TXT/Markdown or text-based PDF through
  `POST /rag/v1/embed`;
- search through `GET /rag/v1/search` with `top_k` from 1 through 20;
- route browser calls through a same-origin Vite proxy.

No RAG server, database, model, vector, chunking, Docker Compose, or packaged
Tauri behavior is changed in this phase.

## Inspected frontend architecture

Confirmed facts:

- Sidebar entries come from `frontend/src/app/routes.ts` and are rendered
  generically by `AppShell`.
- Section identity and URL resolution use Zustand plus browser history through
  `useUiStore.ts` and `sections.ts`; React Router is not used.
- Page selection is performed in `frontend/src/app/App.tsx`.
- Network operations are kept in `frontend/src/shared/api`, with TanStack Query
  hooks in `queries.ts`.
- Browser Agent Server calls already use a same-origin Vite proxy while the
  upstream target is configured in `vite.config.ts`.
- UI styling uses CSS modules and the shared design tokens.

## Architecture decisions

Decisions for this implementation:

- Create a dedicated `ragClient.ts`; page components will not call `fetch`
  directly.
- Use TanStack Query mutations for both explicitly submitted operations,
  including the read-only GET search.
- Browser code calls `/rag-server/rag/v1/embed` and
  `/rag-server/rag/v1/search`; Vite removes `/rag-server` and forwards to the
  configured RAG upstream.
- Default the host-run Vite upstream to `http://127.0.0.1:8765`, configurable
  with `VITE_RAG_SERVER_BASE_URL`.
- For the Compose frontend, set that upstream to
  `http://host.docker.internal:8765` and map `host.docker.internal` through
  Docker's `host-gateway` alias. The browser still calls only `/rag-server`.
- Do not expose `127.0.0.1:8765` as a browser-side URL. From a remote browser,
  that address would refer to the browser machine rather than the Nexgent host.
- Preserve result order and label the score as cosine similarity, never as
  confidence, probability, or accuracy.

## API contracts used

### `POST /rag/v1/embed`

- Request: `multipart/form-data`, one `file` field.
- Supported UI extensions: `.txt`, `.md`, `.pdf`.
- Success body: `{"ok": true}`.
- Repeated upload may create duplicate rows because deduplication is not
  implemented.
- PDF support is limited to PDFs with extractable text; scanned/image-only PDFs
  and OCR are unsupported.

### `GET /rag/v1/search`

- Query parameters: required non-empty `query`; optional integer `top_k`.
- `top_k` defaults to 5 and must be between 1 and 20.
- Results contain `id`, cosine `similarity`, and `context`, in ranked server
  order.

## User experience decisions

- Embedding is file-upload only; no raw-text editor is introduced.
- The selected filename, supported types, pending state, explicit success, and
  API error are visible. The UI does not retry automatically.
- Search validates query and `top_k`, exposes pending/error states, and renders
  rank, cosine similarity, and context with source line breaks preserved.
- The page uses an accessible two-tab segmented control and existing Nexgent
  tokens/forms rather than a new design system.

## Validation

Completed from `frontend/` without starting the RAG server or making live API
requests:

```bash
npm test -- src/shared/navigation/sections.test.ts src/shared/api/ragClient.test.ts src/features/rag/RagPage.test.tsx
npm test
npm run build
```

Measured results:

- Focused RAG/navigation tests: 3 files and 27 tests passed.
- Full frontend suite: 14 files and 94 tests passed.
- `npm run build`: `tsc --noEmit` passed and Vite 8.1.3 completed the production
  build successfully.
- Client tests confirmed the `file` multipart field, browser-generated
  multipart boundary, GET query encoding, default/explicit `top_k`, validation,
  FastAPI error parsing, successful response parsing, and result-order
  preservation.
- Page tests covered initial/file-selected states, supported-extension checks,
  embed pending/success/error states, tab selection, search validation and
  pending/error states, ordered ranks, cosine-similarity wording, and context
  line breaks.

No live embed, search request, ingestion, or database write was performed.

## Known limitations and deferred integration

- Duplicate ingestion remains allowed; the UI will warn against repeated
  uploads but will not invent a deduplication policy.
- The Compose frontend is configured to reach the host-run RAG process through
  `host.docker.internal:8765`. This requires the RAG listener and host firewall
  to permit connections through the Docker host-gateway path.
- The configuration has not taken effect in the existing frontend container
  yet; that container must be recreated manually and then validated.
- Packaged Tauri connectivity and CSP configuration are deferred.
- Browser-to-RAG traffic remains same-origin through Vite, so no RAG CORS change
  is needed and the upstream address is not exposed in browser code.
- This is an internal development/service-integration topology, not a final
  production ingress. TLS, authentication, authorization, upload limits,
  observability, and a hardened reverse-proxy/API boundary remain unresolved.

## Remaining work

- Perform a later manual browser validation without repeating an uploaded
  document.
- Recreate only the frontend container so Docker applies its new environment
  and host-gateway mapping.
- Validate name resolution, container-to-host reachability, and the same-origin
  Vite proxy before using the RAG page.
- Decide packaged Tauri connectivity and the final production ingress/API
  boundary separately.

## Files created and changed

Created:

- `frontend/src/features/rag/RagPage.tsx`
- `frontend/src/features/rag/RagPage.module.css`
- `frontend/src/features/rag/RagPage.test.tsx`
- `frontend/src/shared/api/ragClient.ts`
- `frontend/src/shared/api/ragClient.test.ts`
- `docs/rag-ui-integration.md`

Changed:

- `compose.yaml`
- `frontend/src/app/App.tsx`
- `frontend/src/app/routes.ts`
- `frontend/src/shared/api/queries.ts`
- `frontend/src/shared/navigation/sections.ts`
- `frontend/src/shared/navigation/sections.test.ts`
- `frontend/src/shared/state/useUiStore.ts`
- `frontend/src/vite-env.d.ts`
- `frontend/vite.config.ts`
- `docs/README.md`

## Chronological implementation log

### 2026-08-20 — Host-run browser integration started

- Confirmed the custom section router, shared API-client boundary, TanStack
  mutation convention, and same-origin Vite proxy precedent.
- Chose `/rag-server` as the browser proxy prefix with loopback port 8765 as the
  host-run Vite default upstream.
- Kept Compose and packaged Tauri topology explicitly out of scope.
- No application code, runtime resource, RAG API, or database state had been
  changed at this checkpoint.

### 2026-08-20 — Navigation and route registration

- Added the `rag` application section at `/rag`.
- Added a `RAG` sidebar item with a Lucide Database icon immediately before
  Settings; the existing generic `AppShell` navigation renderer required no
  change.
- Added deterministic coverage for canonical and trailing-slash route
  resolution plus sidebar ordering.

### 2026-08-20 — Centralized client and browser proxy

- Added a typed RAG client for multipart file embedding and GET search. The
  client validates search inputs, parses FastAPI errors, validates successful
  response shapes, and preserves returned result order.
- Added TanStack Query mutation hooks for explicit embed and search actions.
- Added `/rag-server` Vite development and preview proxies. The configurable
  upstream defaults to `http://127.0.0.1:8765`, while browser requests remain
  same-origin under the `/rag-server` prefix.
- No multipart `Content-Type` is set manually; the browser supplies its boundary.

### 2026-08-20 — RAG page implemented

- Added the `/rag` page with accessible Embedding and Search tabs.
- Embedding accepts one `.txt`, `.md`, or `.pdf` file, shows its filename,
  validates the extension, disables invalid/pending submission, and exposes
  explicit success and error states. It includes the scanned-PDF limitation and
  duplicate-ingestion warning.
- Search defaults `top_k` to 5, enforces the integer range 1–20, and disables
  blank, invalid, or pending submissions.
- Search results remain in server order and show array-derived rank, cosine
  similarity, and context with line breaks preserved.
- Added deterministic presentation/helper coverage for initial, selected-file,
  invalid, pending, success, error, tab, top-k, and ordered-result states.

### 2026-08-20 — Deterministic validation complete

- Focused validation passed with 27 tests across the navigation, RAG client,
  and RAG page test files.
- The full frontend suite passed all 94 tests across 14 files.
- TypeScript checking and the Vite production build passed through
  `npm run build`.
- No Uvicorn process, live RAG request, file ingestion, or database write was
  used for this validation.
- Manual host-run Vite/browser validation remains a separate next step.

### 2026-08-20 — Compose frontend host-gateway configuration

- Confirmed the host-run RAG API is expected at port 8765 and retained the
  same-origin browser paths under `/rag-server`.
- Added `host.docker.internal:host-gateway` to the frontend service and set its
  `VITE_RAG_SERVER_BASE_URL` to `http://host.docker.internal:8765`.
- No Vite source change was needed because the proxy already reads that
  environment variable and removes the `/rag-server` prefix.
- The existing frontend container was not restarted or recreated. The mapping
  and upstream therefore remain pending manual application and validation.
- No CORS, backend, RAG server, database, GPU, model, or application-runtime
  setting was changed.
- This host-gateway route is an internal development/service-integration step,
  not the final production ingress or security boundary.
