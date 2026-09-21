# Agents Co-worker Catalog Refinement

Date: 2026-09-10

## Update: Sumin registration

Date: 2026-09-17

Sumin is registered in the frontend co-worker catalog at `/agents`. Its card
describes the existing Slack-to-Nextcloud archive and channel-scoped file
discovery behavior, links to `/agents/sumin`, and does not expose a Chat action
or claim unobserved readiness. Its card points users to Slack as the operating
surface instead of implying a frontend workspace. The generic detail page now
renders its Chat button only for catalog entries that declare `canRunInChat`,
so Sumin's detail route does not imply an unsupported frontend runner.

## Implemented

The Agents menu now opens a focused “Your co-workers” catalog. It uses distinct
Reporting, Knowledge, and Research identities, short descriptions of useful
outcomes, two capability bullets, and explicit actions for each co-worker.
The sidebar remains named Agents and existing routes remain unchanged.

- Weekly Reporter and Scout have Open workspace links to their existing
  specialized pages. RAG has Start chat plus a secondary Details link, with its
  text-only restriction visible before opening Chat. Opening a workspace does
  not launch a job; Start chat selects RAG without sending a message.
- Local Find a co-worker search matches identity, existing catalog metadata,
  and the new user-facing descriptions/capabilities. It has visible counts,
  Escape/clear controls, and a no-results state. It is independent of the
  removed global search field and resets when the catalog unmounts.
- Selected in Chat communicates the current Chat selection without implying a
  running job. Existing readiness is shown only when supplied by the catalog;
  no health/run history is fabricated for RAG or Scout.
- Runtime technology labels and raw run counts were removed from catalog
  cards. Preview cards retain explicit Preview data labeling. Current work is
  displayed only when the catalog supplies an observation mode and work text.
- Loading uses a quiet skeleton with a live status label. Errors hide stale
  cards and offer a real query retry. Empty and filtered-empty states have
  different copy, with Clear search when relevant.
- Cards use 8px corners, restrained role colors, visible keyboard focus, native
  links, and 3/2/1 columns at wide/medium/narrow widths. Titles wrap instead of
  truncating. No decorative dashboard panels or additional navigation tabs.

## Boundaries and decisions

All changes are frontend presentation and interaction. The catalog still comes
through useAgentCatalog. Friendly copy and icons for the three known catalog
IDs live in the Agents page; unknown co-workers fall back to their existing
role, description, and capabilities. Search covers both presentations.

Native links replace the broad article click handler, providing predictable
keyboard and modified-click behavior. The existing Chat selection helper still
clears pending run intent. Shared API adapters, backend services, specialized
workspaces, generic detail pages, application navigation, CSP, Tauri permissions,
and dependency manifests are unchanged.

This refines the catalog layout described in agents-management-interface.md;
older route history in that document is not a description of this change.

## Validation

- `npm test`: 23 test files and 247 tests passed, including catalog search,
  loading/error behavior, action availability, readiness, and RAG restrictions.
- `npm run build`: passed. Vite reports a non-blocking warning for the main
  JavaScript chunk (approximately 504 kB minified / 152 kB gzip); bundle splitting
  was not introduced as part of this catalog-only change.
- `git diff --check`: passed for the frontend changes.
- Standard `cargo check --manifest-path src-tauri/Cargo.toml` encountered the
  existing stale workflow-helper generated-permissions path. The isolated check
  `CARGO_TARGET_DIR=/tmp/nexgent-chat-ux-cargo cargo check --offline
  --manifest-path src-tauri/Cargo.toml` passed.
- `npm audit --audit-level=moderate --cache /tmp/nexgent-chat-npm-cache` reported
  the two existing moderate Vitest/@vitest/mocker findings (GHSA-82fw-gwwq-j7x9).
  No dependency update was applied.
- Browser smoke checks passed at 1440px, 1024px, and 760px. Verified search by
  outcome, result counts, no-results clearing/focus, no horizontal/card overflow,
  RAG Chat selection, selected context on return, details/workspace navigation,
  keyboard Enter activation, no accidental API mutations, and no runtime errors.
  Screenshots were reviewed at wide and narrow widths.

## Preview and reproduce browser checks

From `frontend/`, preview normally with `npm run dev -- --host 127.0.0.1` or use
`npm run dev -- --host 0.0.0.0` for a LAN preview. Browser checks use optional
Playwright tooling outside project dependencies:

```bash
npm install --prefix /tmp/nexgent-chat-ui-tools --no-package-lock playwright@1.63.0
PLAYWRIGHT_BROWSERS_PATH=/tmp/nexgent-chat-ui-tools/browsers node /tmp/nexgent-chat-ui-tools/node_modules/playwright/cli.js install chromium
npm run dev -- --host 127.0.0.1 --port 5187
```

With that preview running, execute in another terminal:

```bash
PLAYWRIGHT_BROWSERS_PATH=/tmp/nexgent-chat-ui-tools/browsers PLAYWRIGHT_MODULE=/tmp/nexgent-chat-ui-tools/node_modules/playwright/index.mjs node scripts/agents-ui-smoke.mjs
```

`AGENTS_UI_URL` overrides the preview URL. Screenshots default to
`/tmp/nexgent-agents-ui-artifacts`; `AGENTS_UI_ARTIFACTS` overrides the location.
Service requests are intercepted with test responses; these checks do not
validate live services or trigger jobs.

## Remaining verification

Live workspace execution and packaged desktop checks were not run for this
presentation change. Use `npm run tauri:dev` on a graphical host to verify the
catalog, keyboard navigation, search, and workspace/Chat links in the packaged
webview. Use `npm run dev -- --host 127.0.0.1` with configured services for live
navigation checks. The existing Cargo cache and dependency audit findings remain
separate follow-up work.
