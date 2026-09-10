# Chat Session UI Upgrade

Date: 2026-09-10

## Update: Continue replies across application menus

Date: 2026-09-10

Switching from Chat to another application menu previously unmounted ChatPage
and aborted its active request. The request coordinator now belongs to App and
is passed into ChatPage. Chat can unmount normally while the same request keeps
updating its original conversation in the session store. Returning displays
partial or completed output without starting a second request; Stop remains
connected to that request. Errors occurring off-screen retain prompt recovery.

This replaces the original stop-on-section-navigation behavior. Explicit Stop,
deleting the generating conversation, and app teardown still cancel the request.
Reloading/closing the app still ends the frontend session. No backend or API
changes were made.

Validation for this update:

- `npm run build`: passed.
- `npm test`: 23 files, 243 tests passed.
- The documented browser smoke command passed, including completion while
  Settings is open, returning through browser history mid-stream and pressing
  Stop, no duplicate requests after returning, and failure recovery after a
  background request fails. Existing cross-conversation, copy, attachment, and
  responsive checks also passed.
- Standard Cargo check still encountered the pre-existing stale permission-file
  path. `CARGO_TARGET_DIR=/tmp/nexgent-chat-ux-cargo cargo check --offline
  --manifest-path src-tauri/Cargo.toml` passed.
- The required npm audit still reports the two existing moderate Vitest findings
  described below. No dependencies changed.

Live-service and packaged Tauri checks remain unverified. Run
`npm run dev -- --host 127.0.0.1` with the configured services, send a message,
switch to Settings during generation, and return to verify the completed reply.
Use `npm run tauri:dev` for the same check in the desktop webview.

## Implemented experience

Chat now uses a centered welcome composer, a bottom composer once messages exist, a readable 780px transcript column, and a collapsible session conversation list. The application navigation remains in place. The removed global search/Pause toolbar is not restored; Chat has compact local navigation and co-worker controls.

- New chat, first-prompt titles (48 characters), inline rename, and confirmed deletion.
- Per-conversation messages, selected co-worker, draft, pending files, failure recovery, and scroll position. Memory-only Zustand state survives section navigation and clears on reload.
- Prompt starters fill the composer without sending. Reuse prompt copies user text into the composer; files must be reattached. Replacing an existing draft/files requires an inline choice.
- Textarea grows to 200px before scrolling; Enter sends, Shift+Enter inserts a newline, and IME composition does not submit.
- File picker, drag-and-drop, and pasted images share the existing validation: five files, 10 MB per file, 25 MB total, and the existing accepted formats. Pending image previews use temporary object URLs that are revoked on removal/unmount. RAG remains text-only and clears pending files with an explanation.
- Replies/code have Copy actions with success/error feedback. Secure Clipboard API failures or absence fall back to a temporary selected textarea and the browser copy command. Focus and text selection are restored afterward. This supports plain-HTTP LAN access without native plugins or permissions. If both browser mechanisms reject copying, a manual-copy hint remains.
- Manual scrolling stops automatic following beyond 80px from the bottom. Jump to latest resumes it. Chat switching restores the conversation's scroll position.
- Placeholder slash commands and simulated execution traces were removed from Chat. Real waiting, streaming, complete, stopped, and failed states replace them. Existing shared mock-run state used by other surfaces was not removed.
- At widths below 1120px, conversations open in a modal drawer with keyboard focus containment, inert background controls, Escape dismissal, and focus restoration. Layouts use existing tokens and corners of 8px or less, with reduced-motion support.

## Architecture and boundaries

`useChatStore` owns session conversations and their UI state. An app-level request coordinator captures the conversation ID, assistant-message ID, co-worker, prompt, and files at submission. Every callback updates that captured conversation, never the currently selected conversation. Replies keep their original speaker label.

Only one request can run at a time. Switching conversations within Chat lets it continue in its original conversation; other composers remain editable and link to the responding chat. Stop, deletion of a generating chat, and app teardown abort the request. Switching application menus keeps the request running. Partial output is retained unless its conversation is deleted. Invalidated callbacks cannot overwrite a newer request or recreate a deleted conversation.

A failed request retains its original prompt/files for explicit recovery without overwriting newer typing. New submissions replace that recovery state. Deleting a conversation releases its stored file references. No files or messages are written to local storage.

API adapters, endpoint URLs, payloads, Rust commands, CSP, capabilities, and dependency manifests are unchanged. Normal chat still submits the latest prompt/files; RAG still submits only its question. Session conversations do **not** add model memory: earlier transcript messages are not sent. The UI states this limitation explicitly. Existing co-worker selections from Agents are bridged through the existing UI store.

## Validation

- `npm test`: passed, 23 files and 243 tests. Added coverage for conversation isolation, titles/deletion/RAG selection, attachment validation, scroll threshold, request switching, duplicate-send prevention, cancellation, late callbacks, failure recovery, and RAG routing.
- `npm run build`: passed (TypeScript and Vite).
- `git diff --check`: passed for the frontend changes.
- Standard `cargo check --manifest-path src-tauri/Cargo.toml` encountered an existing stale build-cache reference to a missing `workflow-helper/.../app_hide.toml`. An isolated build passed with `CARGO_TARGET_DIR=/tmp/nexgent-chat-ux-cargo cargo check --offline --manifest-path src-tauri/Cargo.toml`.
- `npm audit --audit-level=moderate --cache /tmp/nexgent-chat-npm-cache` ran with registry access and reported two existing moderate findings in `vitest` / `@vitest/mocker` ([GHSA-82fw-gwwq-j7x9](https://github.com/advisories/GHSA-82fw-gwwq-j7x9)). Dependency updates are outside this UI change; no audit fix was applied.
- `scripts/chat-ui-smoke.mjs`: passed using mocked HTTP streams and the real rendered UI at 1440px, 1024px, and 760px. It covers welcome prompts, input sizing/IME/newlines, cross-chat streaming, copy/code actions, attachment picker/drop/paste, RAG restrictions, failure recovery, manual scrolling, rename/delete, section navigation, drawer focus, reload behavior, and clipboard fallback. Actual user-message and assistant-message copying also passed from an insecure `http://nexgent-chat.test` origin where `window.isSecureContext` is false and `navigator.clipboard` is absent; that test origin is routed locally by Playwright.

## Run and reproduce

Run commands from `frontend/`. Normal local preview:

```bash
npm run dev -- --host 127.0.0.1
```

LAN preview:

```bash
npm run dev -- --host 0.0.0.0
```

The browser suite uses optional tools outside project dependencies. Install the validated tool version and its Chromium browser:

```bash
npm install --prefix /tmp/nexgent-chat-ui-tools --no-package-lock playwright@1.63.0
PLAYWRIGHT_BROWSERS_PATH=/tmp/nexgent-chat-ui-tools/browsers node /tmp/nexgent-chat-ui-tools/node_modules/playwright/cli.js install chromium
```

Start the dedicated preview in another terminal, then run the smoke checks:

```bash
npm run dev -- --host 127.0.0.1 --port 5187
```

```bash
PLAYWRIGHT_BROWSERS_PATH=/tmp/nexgent-chat-ui-tools/browsers PLAYWRIGHT_MODULE=/tmp/nexgent-chat-ui-tools/node_modules/playwright/index.mjs node scripts/chat-ui-smoke.mjs
```

Override `CHAT_UI_URL` if using another port. Screenshots default to `/tmp/nexgent-chat-ui-artifacts`; `CHAT_UI_ARTIFACTS` overrides that location. The script intercepts Chat requests and health checks; it does not invoke a live chat service. Browser startup and preview port binding may require execution outside a restricted sandbox.

## Limits and follow-up

No persisted chat history, multi-turn backend memory, branching, regeneration, voice, sharing, or backend feedback submission was introduced. The session list is organizational UI only.

Live-service and packaged Tauri end-to-end checks were not run. For live integration, run `npm run dev -- --host 127.0.0.1` with the existing configured services and send a normal message/file and a RAG question. For packaged-webview validation, run `npm run tauri:dev` on a graphical host and verify Copy, file selection, streaming Stop, and section navigation. Recheck the standard Cargo command after repairing the pre-existing build cache, and address the Vitest audit findings in a separate dependency update.
