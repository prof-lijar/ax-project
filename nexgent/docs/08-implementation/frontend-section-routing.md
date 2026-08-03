# Frontend Section Routing

Date: 2026-08-03

## Implemented

Every left-sidebar section now has a stable browser route:

| Section | Route |
| --- | --- |
| Workspace | `/workspace` |
| NextCloud | `/nextcloud` |
| Tasks | `/tasks` |
| Approvals | `/approvals` |
| Co-workers | `/co-workers` |
| Activity | `/activity` |
| Settings | `/settings` |

Sidebar items are links with real `href` values and use client-side navigation
for ordinary clicks. Workspace shortcut buttons use the same navigation path.
Direct page loads select the section represented by the URL, and browser
Back/Forward events synchronize the visible section with the restored route.
The root path and unknown paths are replaced with `/workspace`.

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
