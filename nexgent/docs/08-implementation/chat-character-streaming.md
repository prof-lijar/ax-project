# Smooth Chat Character Streaming

Date: 2026-09-22

## Implementation

Chat previously rendered each cumulative server update immediately, making
responses jump by words or chunks. The shared transcript now uses a per-message
presentation buffer for both persistent AX chat and RAG chat. Incoming content
remains authoritative in the chat store; animation does not delay network reads,
persistence, cancellation, or server run state.

`frontend/src/features/chat/useStreamingText.ts` reveals new text on animation
frames, usually one character per frame (roughly 60 characters/second at 60 Hz).
Large backlogs gradually accelerate to at most four characters per frame. Frame
elapsed time is capped so returning from a suspended tab does not dump a backlog.
`Intl.Segmenter` keeps emoji and combining characters together; older webviews
without that API fall back to Unicode code points. TypeScript includes the
`ES2022.Intl` declarations; the JavaScript build target remains ES2020.

`ChatTranscript` isolates animation in each message row and follows the bottom
on display updates only while the conversation's existing follow mode is active.
Completion indicators and message copy actions wait until queued display text is
revealed. Saved messages and the existing prefix of a rejoined response render
immediately. Stopped/failed replies reveal all received text immediately and cancel
animation. Authoritative replacements reconcile immediately. Unmounting cancels
pending animation frames. Backend APIs, stored messages, and CSP are unchanged.

## Validation

Passed from `frontend/`:

```bash
npm run build
npm test
CARGO_TARGET_DIR=/tmp/nexgent-cargo-check cargo check --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
git diff --check
```

All 273 existing tests passed. The dependency audit reported zero vulnerabilities.
The production build retains the existing warning about a bundle over 500 kB.

Added `scripts/chat-streaming-ui-smoke.mjs`, which mounts the real transcript in
Chromium under React Strict Mode with deterministic animation frames. All 15
checks passed: chunk buffering, individual character prefixes, final-chunk draining,
exact final text, idle cleanup, saved history, rejoining, emoji, combining marks,
replacements, stop, failure, auto-follow, preserving scroll position, and unmount.

Run the browser regression with Vite in one terminal:

```bash
npm run dev -- --host 127.0.0.1 --port 5187
```

Then, with Playwright and Chromium available (the following paths were used here):

```bash
PLAYWRIGHT_BROWSERS_PATH=/tmp/nexgent-chat-ui-tools/browsers \
PLAYWRIGHT_MODULE=/tmp/nexgent-chat-ui-tools/node_modules/playwright/index.mjs \
node scripts/chat-streaming-ui-smoke.mjs
```

## Limitations and Remaining Verification

The browser regression exercises actual UI rendering with controlled content; it
does not invoke a live model, authenticated backend, or the packaged Tauri webview.
For a live end-to-end check, run `npm run dev -- --host 127.0.0.1`, sign in, and send
a multi-paragraph prompt to AX and RAG. For native visual verification, run
`npm run tauri:dev` and repeat. Those live checks were not run because this change
was validated with an isolated browser fixture without account/model requests.

The display cannot reveal text before it arrives from the server. Markdown may
reflow as delimiters finish, and unusually large backlogs can take time to drain.
The Stop control still reflects server run state and may disappear while the
last display characters finish. Older webviews using the code-point fallback
protect surrogate pairs but do not group multi-code-point graphemes.
