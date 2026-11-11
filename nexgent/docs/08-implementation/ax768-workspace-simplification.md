# AX768 workspace simplification

Date: 2026-11-11

## Implemented

Refactored `/agents/ax768` into a compact operational workspace. Workflow is
now the initial view; the existing Test view is labeled **Individual tasks /
개별 작업**, followed by Sheets. Existing tab IDs, keyboard navigation and
mounted panels preserve drafts and in-flight requests across tab changes.

- Reduced the page header and removed its promotional subtitle.
- Grouped workflow selection, request text, images and execution into one
  request panel. Required selection and inline validation/focus remain intact.
- Combined workflow status and output into one result panel. The response,
  candidate choices and notices precede five expandable stage receipts.
  Failures, disconnected signals, uncertain writes and member issues expand
  automatically; successful receipts remain available on demand.
- Moved upload instructions, task descriptions, search attempts and session
  history into native expandable sections. Selected workflows still disclose
  that confirmed signals lead to AS and member-note updates.
- Simplified Sheets to named links without internal aliases or case IDs.
- Retained Korean/English copy, existing design tokens, visible keyboard focus,
  responsive stacking, upload/OCR review, candidate reruns and verified receipts.
  Status labels wrap at narrow widths; meaning does not depend on color alone.

This is a frontend presentation change. Runtime graphs, API payloads,
authentication, authorization, persistence and business rules are unchanged.
No dependencies or global configuration were changed.

## Source and serving checkout

The requested URL, `http://192.168.0.18:5173/agents/ax768`, serves the primary
checkout at `/home/nextor-ai-02/nextor_ai/ax-project/nexgent/frontend`.
The scoped changes were applied there and to the sibling `frontend/` of the
914e worktree. Existing worktree edits were preserved. Vite serves the changes
without a process restart; no production deployment was performed.

Changed components: `Ax768WorkbenchPage`, `Ax768WorkflowPanel`,
`Ax768SheetsPanel`, their CSS modules, Korean translations and affected checks.
`StageDetails` is a local presentation helper, not a shared runtime abstraction.

## Validation

Validation used `/tmp/ax768-ui-refactor/frontend`, a temporary copy of the
serving frontend with the identical lockfile and existing matching dependencies.
From `nexgent/frontend`, the equivalent commands are:

```bash
npm run build
npm test -- src/features/agents src/shared/api/ax768Client.test.ts src/shared/api/ax768MemberNote.test.ts src/shared/api/ax768WorkflowClient.test.ts src/shared/state/useAx768Store.test.ts src/shared/i18n/i18n.test.tsx
CARGO_TARGET_DIR=/tmp/ax768-ui-refactor/cargo-target cargo check --offline --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
```

- Production build passed; the existing large-chunk warning remains.
- All 164 tests in 12 focused files passed.
- Offline Cargo check passed.
- Audit reported the existing eight findings: four low, two moderate and two
  high, involving Vitest/mocker, KaTeX consumers, source-map-js and Vite. Fixing
  dependency versions is separate follow-up work.
- `git diff --check` passed in both checkouts.

Browser checks ran against the actual URL in Chromium, with all product APIs
intercepted and synthetic account/workflow responses. No real AS, sheet or
member records were changed. Reproduce using the existing local browser:

```bash
export PLAYWRIGHT_MODULE=/tmp/ax768-browser/node_modules/playwright/index.mjs
export PLAYWRIGHT_CHROMIUM_EXECUTABLE=/home/nextor-ai-02/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell
export AX768_TEST_URL=http://192.168.0.18:5173
node scripts/ax768-ui-smoke.mjs
node scripts/ax768-workflow-member-note-smoke.mjs
node scripts/ax768-member-note-smoke.mjs
node scripts/ax768-ocr-smoke.mjs
```

The browser scripts also accept other installed Playwright/browser paths.
All four passed: default view, keyboard tabs/disclosures, missing-input focus
and no dispatch, disabled future workflows, execution lock, candidate reruns,
draft persistence, clearing/reload, collapsed successful receipts, expanded
uncertain member writes, power/no-AS and disconnected results, individual
member tasks, and actual local Korean OCR with editable text and removal
cancellation. Korean/English initial views were checked at 1280, 820 and 390px;
secondary views and successful receipts were also checked on narrow screens.
Screenshots under `/tmp/ax768-ui-refactor/` were reviewed; no horizontal overflow
or browser page errors occurred.

Live authenticated backend/Agent Server execution was not exercised because
this UI verification used synthetic records. For an integrated check, run
`npm run dev -- --host 0.0.0.0`, sign in as an administrator, open
`/agents/ax768`, and execute the selected workflow against an approved test
record; confirm the displayed receipt against that record. This writes real
AS/member data under the existing workflow policy.

## Update: input help removed (2026-11-11)

Removed the requested **입력 도움말 / Input help** disclosure and its contents
from the Workflow composer in both checkouts. Removed the textarea's reference
to the deleted hint. Upload validation and OCR review remain unchanged.
The production build and `node scripts/ax768-ui-smoke.mjs` passed again using
the environment above; the browser check confirms the disclosure is absent.

## Update: workflow update sentence removed (2026-11-11)

Removed “신호가 확인되면 AS 기록과 회원 메모를 업데이트합니다.” and its
English equivalent from the composer at the user's request in both checkouts.
Removed the now-unused selected-workflow lookup. Workflow execution is
unchanged. The production build and `git diff --check` passed; this copy-only
change did not require another browser interaction run.
