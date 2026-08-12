# Agent Server Chat

Date: 2026-08-10

## Update: Run Cancellation on Stop

Date: 2026-08-10

Chat stream requests now set the Agent Server's `on_disconnect` policy to
`cancel`. The server otherwise defaults to continuing a run after the client
disconnects, so aborting the browser request stopped the UI stream without
stopping the graph or its active LLM HTTP stream. The continued generation
could occupy the model and leave a subsequent message waiting.

The Stop control still aborts the browser request through `AbortController`.
That disconnect now instructs Agent Server to cancel the stateless run; async
cancellation propagates through the chat graph to the provider stream. The
request remains stateless and does not require a separately managed thread or
run-cancellation endpoint.

## Update: Health Query Result

Date: 2026-08-10

The successful `/ok` client now returns an explicit `true` value. Previously it
resolved with `undefined`, which TanStack Query rejects as invalid query data;
that made the Chat header report `Server unavailable` even while chat requests
were succeeding. A regression assertion now verifies the explicit result.

## Update: Markdown Responses

Date: 2026-08-10

Assistant messages now render Markdown with GitHub-flavored tables, task lists,
and strikethrough support. Headings, lists, blockquotes, links, inline code,
fenced code blocks, tables, and images use chat-specific responsive styling.
User messages remain plain text. Raw HTML is not enabled, external links open in
a separate browsing context with `noreferrer`, and a rendering regression test
confirms that raw script markup is not emitted.

## Update: Incremental Response Rendering

Date: 2026-08-10

The Agent Server workflow now forwards provider text chunks as safe LangGraph
`custom` events. The client concatenates each `response_delta` while the SSE
body is being read, creates one assistant message on the first delta, and
replaces its Markdown content as later deltas arrive. A streaming cursor and
continuous auto-scroll remain active until the terminal `values.response`
verifies the completed text. Cancellation or failure preserves the most recent
partial response, and duplicate submissions stay disabled for the full run.

## Summary

The frontend Workspace/Mission Control section was replaced by a focused Chat
section at `/chat`. Chat connects to the existing AX Agent Server, reports its
availability, sends one message per stateless run, and displays the final
assistant response from the server's SSE stream.

The old Mission Control page and its workspace-only frontend query, mock data,
TypeScript types, Rust command, domain model, and seed data were deleted. The
sidebar keeps `AX Project` as a static product subtitle. Root, unknown, and the
former `/workspace` route now resolve to `/chat`.

## Architecture and Configuration

- `src/shared/api/agentServerClient.ts` owns health and chat requests. UI code
  does not contain `fetch` or SSE parsing logic.
- `GET /ok` confirms availability by HTTP success. No undocumented response
  schema is assumed.
- `POST /runs/stream` sends only the current message with `assistant_id` set to
  `chat`, `stream_mode` set to `custom` plus `values`, and `on_disconnect` set
  to `cancel`. Transcript history is never sent.
- The incremental SSE parser buffers partial lines, handles LF and CRLF records,
  preserves split UTF-8 characters, accumulates validated custom text deltas,
  ignores metadata, and verifies the final `values.response` after end-of-stream.
- Zustand stores user and assistant messages in memory. Navigation preserves
  the transcript; a browser or desktop reload clears it.
- An `AbortController` disconnects the active request, and the request's Agent
  Server policy cancels the associated run. The UI also distinguishes HTTP,
  network, cancellation, missing-body, malformed-event, and missing-final-
  response states.

The upstream is configured at build/start time:

```bash
VITE_AGENT_SERVER_BASE_URL=http://192.168.0.18:2024
```

That LAN URL is the default when the variable is omitted. Ordinary browser
development and preview request the same-origin `/agent-server` path, which
Vite proxies to the configured upstream to avoid CORS and Private Network Access
failures. The packaged Tauri runtime uses the configured upstream directly. Its
strict CSP allows the default endpoint only; a different packaged endpoint must
also be added explicitly to `connect-src` before rebuilding.

No provider keys or other credentials are read, stored, or sent by this client.
The gateway on port 8080 is not used.

## Operation

Run the browser development server:

```bash
npm run dev -- --host 127.0.0.1
```

Run the packaged-web preview proxy:

```bash
npm run build
npm run preview
```

Override the Agent Server for either Vite command:

```bash
VITE_AGENT_SERVER_BASE_URL=http://agent-host:2024 npm run dev -- --host 127.0.0.1
```

## Validation

Completed from `frontend/`:

```bash
npm test
npm run build
CARGO_TARGET_DIR=/tmp/nexgent-cargo-check cargo check --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
```

All 17 client/parser and Markdown rendering tests passed. They cover one-byte
network chunks, split multibyte text, CRLF/LF events, custom delta accumulation,
EOF flushing, final-response verification, ignored metadata, malformed and
empty streams, the exact single-message and cancel-on-disconnect request body, health requests,
cancellation, HTTP/network failures, common Markdown structures, and raw HTML
suppression. The
TypeScript/Vite production build and Rust check also passed.
The dependency audit reported zero vulnerabilities after safe transitive patch
updates for `nanoid` and `postcss`.

## Known Limitations and Remaining Verification

The operator subsequently confirmed that Agent Server health and completed chat
runs work. The new custom-event token stream still requires container rebuild
and live end-to-end verification because this implementation environment cannot
access the Docker socket. Perform the remaining check with:

```bash
sudo docker compose up --build -d agent-server frontend
npm run dev -- --host 127.0.0.1
```

Then open `http://127.0.0.1:5173/chat`, confirm the availability indicator, send
a message, verify that its content grows before completion, and cancel a second
request while it is active. Confirm in the model server metrics or logs that
generation stops, then immediately send another message and verify that it
starts without waiting for the canceled generation. The Agent Server remains
stateless, so the visible transcript is presentation state rather than backend
conversation memory.
