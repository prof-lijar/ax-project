# Compact Agent Catalog Cards

Date: 2026-09-28 (Asia/Seoul)

## Implementation

The `/agents` catalog now uses smaller cards with a combined icon/name/status row, a two-line purpose description, and compact actions. Removed the separate specialty heading, capability bullets, and current-work block from the catalog card. Capability metadata remains available to existing search logic. Name/detail links and the existing Chat/workspace routing behavior remain intact, including Slack-only details, Chat selection state, preview/readiness badges, and the RAG text-only indicator.

`AgentsPage.module.css` reduces card padding from 24px to 16px, grid gaps from 18px to 12px, avatars from 44px to 32px, name text from 19px to 15px, and primary control height from 38px to 32px. The description has no fixed minimum height and is clamped to two lines with its full text available in the DOM and title attribute. Cards use an auto-fill grid with a 280px minimum capped at available width; footers wrap to accommodate narrow layouts. Loading placeholders and page spacing are also reduced. Existing tokens and 8px card radii are retained.

Files: `frontend/src/features/agents/AgentsPage.tsx`, `AgentsPage.module.css`, and `AgentsPage.test.tsx`. The existing Sumin rendering assertion now checks its retained purpose description instead of the removed capability list. No new dependencies or product operations were introduced.

## Validation

From `frontend/`:

- `npm test`: 304 tests passed across 30 files, including catalog states and routing/action assertions.
- `npm run build`: passed; the existing bundle-size warning remains.
- `npm audit --audit-level=moderate`: zero vulnerabilities.
- `git diff --check`: passed.
- `cargo check --manifest-path src-tauri/Cargo.toml`: encountered the pre-existing stale Tauri permission path referencing `workflow-helper`. The clean-cache alternative passed:

```bash
CARGO_TARGET_DIR=/tmp/nexgent-language-cargo cargo check --offline --manifest-path src-tauri/Cargo.toml
```

The requested preview URL responded HTTP 200 to `curl -sS -I --max-time 10 http://192.168.0.18:5173/agents`. This checks reachability only, not authenticated rendering. No browser runtime was available for visual verification.

## Remaining visual verification

Use the running preview at `http://192.168.0.18:5173/agents`, or start it from `frontend/` with:

```bash
npm run dev -- --host 0.0.0.0
```

Sign in and check Korean/English card wrapping at narrow and wide desktop widths, search/empty/loading states, keyboard focus, and each agent's Chat/detail/workspace action. Exact rendered card heights have not been measured in a browser.
