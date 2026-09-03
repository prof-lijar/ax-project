# Frontend Section Routing

Date: 2026-08-03

## Update: Retired Tasks, Approvals, and Activity Routes

Date: 2026-09-03

The Tasks, Approvals, and Activity sections were removed from the frontend
navigation and route model. Their former paths (`/tasks`, `/approvals`, and
`/activity`) now resolve as unknown locations and are replaced with the Chat
fallback at `/chat` during application synchronization. Focused route tests
verify that the three identifiers are absent from the sidebar and that their
former URLs remain unresolved.

The current flat sidebar routes are:

| Section | Route |
| --- | --- |
| Chat | `/chat` |
| NextCloud | `/nextcloud` |
| Agents | `/agents` |
| Test agent | `/test-agent` |
| RAG | `/rag` |
| Settings | `/settings` |

Agent detail URLs continue to use `/agents/:id`. The `/co-workers` compatibility
path continues to normalize to `/agents`.

## Update: Agent Detail Routes

Date: 2026-08-14

The existing History API router now recognizes one dynamic route shape,
`/agents/:id`, in addition to the flat section paths. Agent detail URLs remain
part of the `agents` section so the sidebar state does not change when moving
between the catalog and a detail page.

Zustand now tracks the active normalized path alongside the active section.
Initial URL synchronization, client-side navigation, and `popstate` updates set
both values atomically. `App.tsx` uses the active path to choose the catalog at
`/agents` or the detail view at `/agents/:id`. Detail IDs are URL-decoded for
catalog lookup, and paths with additional segments remain unresolved.

Focused route tests cover the canonical list path, detail paths, trailing-slash
normalization, decoded IDs, unknown nested paths, the existing legacy
`/co-workers` redirect, and the Weekly Reporter test route. See
[Agents Management Interface](agents-management-interface.md) for the detail
UX, sequential mock ID mapping, frontend-only execution boundary, and complete
validation record.

## Update: Canonical Agents Route

Date: 2026-08-13

The former Co-workers navigation item and `/co-workers` path were replaced by
Agents at `/agents`. Direct requests to `/co-workers`, with or without a
trailing slash, are normalized to `/agents` so existing links remain valid.
The compatibility path selects the same Agents section and is replaced in
browser history rather than adding an extra navigation entry.

Route resolution tests cover the canonical path, compatibility redirect,
trailing-slash normalization, and unknown-path behavior. See
[Agents Management Interface](agents-management-interface.md) for the feature
design, data boundary, validation, and remaining live integration work.

## Implemented

The initial implementation gave every left-sidebar section a stable browser
route. Tasks, Approvals, and Activity were subsequently retired as documented
in the 2026-09-03 update above:

| Section | Route |
| --- | --- |
| Workspace | `/workspace` |
| NextCloud | `/nextcloud` |
| Tasks | `/tasks` |
| Approvals | `/approvals` |
| Co-workers | `/co-workers` |
| Activity | `/activity` |
| Settings | `/settings` |

At that time, sidebar items were implemented as links with real `href` values
and client-side navigation for ordinary clicks. Workspace shortcut buttons used
the same navigation path. Direct page loads selected the section represented by
the URL, and browser Back/Forward events synchronized the visible section with
the restored route. The root path and unknown paths were originally replaced
with `/workspace`; the current `/chat` fallback is documented above.

## Architecture Decisions

- Routing uses the browser History API and the existing Zustand UI store. No
  routing dependency was added for this small, flat route map.
- Route paths live in `src/shared/navigation/sections.ts` and sidebar metadata
  references that map, keeping section identifiers and paths in one source of
  truth that both app-shell and feature navigation can use.
- Modified-click behavior on sidebar links is preserved, while ordinary clicks
  are handled without a full page reload.
- Section selection remains ephemeral UI state; the URL is now the source used
  to restore that state on initial load and history navigation.

## Run Commands

From `frontend/`:

```bash
npm run dev -- --host 127.0.0.1
```

Open a route directly, for example:

```text
http://127.0.0.1:5173/nextcloud
```

## Validation

- `npm run build` passed, including TypeScript checking and the Vite production
  build.
- `CARGO_TARGET_DIR=/tmp/nexgent-cargo-check cargo check --manifest-path src-tauri/Cargo.toml`
  passed.
- Direct HTTP requests to all seven routes on the running Vite server returned
  status `200`.
- `git diff --check` passed.

## Known Limitations and Follow-up

- Browser history interaction was reviewed in code but not exercised through
  an automated browser test because the repository has no browser automation
  setup. Remaining manual verification: run the development command above,
  visit each sidebar section, then use browser Back and Forward to confirm the
  URL, selected navigation item, and visible section remain synchronized.
- Any future production web server must serve `index.html` as the fallback for
  these client-side paths. Vite development already provides this fallback;
  the Tauri desktop entry continues to load the bundled application normally.
