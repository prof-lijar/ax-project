# English and Korean Interface Language

Date: 2026-09-28 (Asia/Seoul)

## Implemented

- Korean is the default for first-time use, invalid preferences, and unavailable browser storage. English is available as an explicit saved preference.
- Language selectors appear in the sidebar, sign-in form, and account settings. Language changes update mounted interface components without remounting the workspace or clearing chat drafts, attachments, requests, or query caches.
- The `nexgent.language` local-storage key contains only `ko` or `en`. The preference is device/browser-origin specific and survives logout. Blocked/full storage allows switching for the current session. Storage changes from other tabs synchronize the language; clearing the preference restores Korean.
- Korean copy covers navigation, accounts/access administration, chat controls and accessibility labels, co-worker catalog/detail views, Scout research/scheduling, NextCloud browsing/viewing, knowledge management/search, and weekly report controls.
- Navigation uses Co-workers / 동료 and Knowledge / 지식 while retaining `/agents` and `/rag` routes.
- Localized counts and schedule phrases support interpolation. Display dates and numbers use the selected locale where applicable; schedule API dates/timezones retain their existing formats and KST semantics.
- HTML starts with `lang="ko"`; the provider updates document language when the preference changes.

## Architecture and boundaries

`frontend/src/shared/i18n/index.ts` owns the Zustand language store, safe persistence, locale selection, and the translation helper. English source copy is the lookup key; `ko.json` contains Korean translations. Missing keys retain their original text. Interpolation uses named/numbered placeholders and does not interpret HTML. Components subscribe to language changes, and helpers resolve current language at call time. No translation dependency or remote translation service was added.

Translate product copy at its presentation boundary. Do not translate user messages, saved conversation titles, report bodies, source passages, filenames, permission keys, service identifiers, or API payloads. Untouched local empty-chat titles are translated for display only. Arbitrary backend error text and remote content remain in their source language; known account errors and local validation messages have Korean copy. The destructive knowledge confirmation token remains exactly `DELETE` in both languages.

This implementation follows the existing web/account and API integration boundaries even though the older architecture guide describes a primarily Rust-command-backed desktop application. No Tauri permissions, CSP rules, credentials, or backend contracts changed.

When adding interface copy, add an English-key/Korean-value pair to `ko.json`, use `t(...)` in the presentation layer, and ensure its containing component subscribes to language changes. Keep stored state independent of localized labels wherever possible.

## Validation

Run from `frontend/`:

```bash
npm test
npm run build
npm audit --audit-level=moderate
cargo check --manifest-path src-tauri/Cargo.toml
```

- `npm test`: 300 tests passed across 29 files. Added coverage for default/invalid/stored language preferences, denied storage, fresh-module restoration, preserving a chat draft during language changes, Korean sign-in/co-worker/knowledge rendering, interpolation, schedule wording, and the unchanged deletion token. Existing workflow tests explicitly select English through `src/testSetup.ts`.
- `npm run build`: passed. Vite still reports a bundle larger than its 500 kB warning threshold.
- `npm audit --audit-level=moderate`: passed, zero vulnerabilities. The first sandboxed attempt could not resolve the npm registry; the permitted network retry succeeded.
- The ordinary Rust command encountered an existing cached Tauri permission path referencing `workflow-helper`. A clean temporary target succeeded:

```bash
CARGO_TARGET_DIR=/tmp/nexgent-language-cargo cargo check --offline --manifest-path src-tauri/Cargo.toml
```

No Rust source changes were required.

## Remaining browser verification

No browser automation/runtime was available in this session, so rendered visual layouts and real authenticated end-to-end switching have not been verified. Start the existing application/backend and run:

```bash
npm run dev -- --host 127.0.0.1
```

At `http://127.0.0.1:5173`, remove `nexgent.language` in browser storage and reload: the sign-in interface should be Korean. Select English, reload, and verify the saved English preference. Sign in and switch on each main route, keeping a draft and selected files, then verify that work is retained. Check sidebar controls at narrow desktop widths and switch in a second tab to verify synchronization. Confirm that report bodies, filenames, source passages, and user messages retain their original content. This changes interface language only; it does not change the language requested from co-workers/models.

## Update: Agents terminology — 2026-09-28

At the user's explicit request, visible English “Co-workers” / “co-worker” wording now uses “Agents” / “agent”; Korean “동료” now uses “에이전트”. This overrides the earlier co-worker terminology preference in the UX/agent guides for these labels. The sidebar and catalog heading are “Agents” / “에이전트”. Catalog search, status/count/empty-state text, accessibility labels, chat agent selection/notices, knowledge helper copy, and Korean agent descriptions use the same terminology. Korean agent counts use “개”.

The `/agents` URL and existing `/co-workers` compatibility redirect remain intact. User-generated content, identifiers, and historical implementation records were not rewritten. Existing catalog and locale assertions were updated; no new behavior or dependencies were added.

Validation from `frontend/`: `npm test` passed (304 tests, 30 files); `npm run build` passed with the existing bundle-size warning; `npm audit --audit-level=moderate` reported zero vulnerabilities; `git diff --check` passed. The standard `cargo check --manifest-path src-tauri/Cargo.toml` still encounters the existing stale Tauri cache path, while `CARGO_TARGET_DIR=/tmp/nexgent-language-cargo cargo check --offline --manifest-path src-tauri/Cargo.toml` passed. The current suite includes the pending Settings profile and password-confirmation changes.

Visual browser verification remains unperformed because no browser runtime is available. Run `npm run dev -- --host 127.0.0.1`, then check `/agents`, `/chat`, and `/rag` in Korean and English, including catalog search/empty states and the sidebar.
