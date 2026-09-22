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

## Update: Single Response Transition

Date: 2026-09-22

The empty assistant turn no longer presents `Thinking…` beneath the co-worker
name. That treatment made the waiting phase look like one response followed by
a second response when answer text arrived. Waiting now renders as a quiet pulse
with a `Waiting for AX` article label; the co-worker name and response semantics
appear once, together with the first real answer text.

Validation passed with `npm run build`, all 273 tests in `npm test`,
`git diff --check`, and 16 deterministic Chromium streaming checks. The browser
regression now specifically verifies that waiting is not rendered as a response.

## Update: Prevent Completed Answers From Clearing and Replaying

Date: 2026-09-22

The preceding waiting-indicator change did not address answer resets. A browser
reproduction using the real history hook, query cache, runner, and transcript
confirmed that completion could be overwritten by cached empty waiting history.
Completion clears `runId` and invalidates history queries. If the detail query
finishes before the messages query, the history effect previously replaced the
completed answer with stale messages because its preservation guard required an
active `runId`. The subsequent message response made the answer reappear and
animate again. Late list/detail metadata could also resurrect that finished run.

`mergeChatHistory.ts` now reconciles immutable message IDs independently of run
state. It preserves terminal replies, prevents partial history from shortening
streamed content, accepts final server replies, retains live messages missing
from older pages, and orders paginated history without duplicating turns. Local
user messages without positions stay ahead of positioned assistant snapshots.
The runner records settled run IDs in session state; list/detail reconciliation
and observer startup ignore those finished runs. Newly discovered runs can still
be observed normally. This changes frontend reconciliation only; it does not
filter or reinterpret model output.

Validation passed:

```bash
npm run build
npm test
CARGO_TARGET_DIR=/tmp/nexgent-cargo-check cargo check --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
git diff --check
```

All 282 unit tests passed. Audit reported zero vulnerabilities; the existing
bundle-size warning remains. The 16 character-streaming browser checks passed.
The new `scripts/chat-history-race-smoke.mjs` failed before the fix with
`Completion was overwritten by stale waiting history` and passed after it. It
verifies the actual mounted history hook under independently delivered detail,
list, and message cache updates, preserving the visible final answer and avoiding
run reactivation or duplicate response rows.

Browser commands (run against a fresh Vite process to avoid stale HMR module
instances in fixtures; port 5188 was used for final validation):

```bash
npm run dev -- --host 127.0.0.1 --port 5188
CHAT_UI_URL=http://127.0.0.1:5188 PLAYWRIGHT_BROWSERS_PATH=/tmp/nexgent-chat-ui-tools/browsers PLAYWRIGHT_MODULE=/tmp/nexgent-chat-ui-tools/node_modules/playwright/index.mjs node scripts/chat-history-race-smoke.mjs
CHAT_UI_URL=http://127.0.0.1:5188 PLAYWRIGHT_BROWSERS_PATH=/tmp/nexgent-chat-ui-tools/browsers PLAYWRIGHT_MODULE=/tmp/nexgent-chat-ui-tools/node_modules/playwright/index.mjs node scripts/chat-streaming-ui-smoke.mjs
```

No authenticated model request or packaged Tauri check was performed. For live
verification, run `npm run dev -- --host 127.0.0.1`, sign in, and submit the reported
SAT planning prompt; verify that the answer remains visible through completion
and a history refresh. The deterministic browser fixture isolates and reproduces
the frontend race without account access or dependence on model timing.
