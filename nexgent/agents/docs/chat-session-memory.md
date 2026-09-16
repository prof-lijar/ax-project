# Chat session memory

Date: 2026-09-14

Normal Chat now includes earlier successful user/assistant turns when generating
a follow-up. A conversation owns a random UUID `sessionId`, separate from its
UI message IDs. Switching conversations and returning preserves the same ID;
a new conversation receives a different one.

## Request and state contract

The frontend sends `prompt`, optional `files`, and `session_id` as multipart
form data to `POST /api/chat/stream`. The backend validates the session as a
UUID and calls `POST /threads/{session_id}/runs/stream` with
`if_not_exists=create`, `multitask_strategy=reject`, and
`on_disconnect=cancel`. A busy thread returns a safe 409 error; callers retry
once the previous run finishes. Requests without a session retain the existing
stateless API behavior. RAG Chat remains a separate, one-turn path.

Agent Server supplies the checkpointer. The graph module does not instantiate
a database connection or process-global memory store. Each completed node
replaces the thread's `history` with a bounded list of `{user, assistant}`
text pairs. The model receives alternating historical messages followed by
the current user message. No client-supplied transcript is accepted by the
backend.

History contains at most 20 complete turns and 32,000 characters in total.
Oldest turns are dropped as whole pairs; the retained history is always a
contiguous recent suffix. If the newest pair alone exceeds the budget, no
history is retained for that turn. This is a character budget for past text,
not a model-specific token limit; existing current-message, attachment, and
response limits still apply. Historical checkpoints remain subject to the
Agent Server's own retention policy; bounding current state does not delete
older checkpoints.

History updates only when generation succeeds. Model failures, cancellation
before node completion, empty replies, and attachment validation errors do not
append a turn. Every session request resets `attachments`, `response`, and
`error` while preserving history. Session requests use only `custom` streams,
and every successful Chat turn emits `response_complete`; previous responses
and stored history are therefore not replayed through `values` events.
A disconnect after server-side completion may still leave that completed turn
in history even if the browser did not receive the final event. Requests are
not deduplicated after completion; a manual retry then creates another turn.

Attachment bytes, extracted text, image data URLs, and file references are not
copied into conversation history. Only the user's prompt and generated answer
are retained, so a later turn can discuss the answer but cannot reopen the
original attachment. Attachment instructions still precede the current
multimodal content and earlier text turns.

## Session lifetime and deployment

The existing frontend store is ephemeral. Memory works while the conversation
is present in the running app, including menu changes and switching chats.
Reloading the page/restarting the app creates new conversations and does not
restore old sessions. Deleting a conversation removes its UI reference; it
does not purge Agent Server checkpoints. Cross-device history, user profiles,
and a server-side conversation listing/deletion API are outside this change.

Storage durability is provided by the deployed Agent Server. The current
`langgraph dev` deployment is a development runtime; this change does not
promise production restart durability or add a production database. An
existing thread can be reused only while the runtime still retains it.
The trusted-LAN/noop-auth limitation remains: UUIDs isolate conversations by
identity, but are not user authorization. A public deployment must enforce
user/tenant ownership of threads at its authenticated gateway.

Roll out Agent Server, backend, and frontend together, with the graph update
first: session requests require the graph's unconditional `response_complete`
event. No dependency additions or database schema migration are required.
The first session-aware frontend load starts new empty sessions; earlier UI-only
messages are not backfilled.

## Validation

- Graph tests exercise follow-up history, thread isolation, graph recreation
  against the same checkpointer, model failure, cancellation, history limits,
  and custom-only completion.
- Backend tests validate UUID handling, thread URL/payload, transient reset,
  conflict errors, attachment cleanup, stateless compatibility, and RAG routing.
- Frontend tests cover stable session reuse, new-chat isolation, switching back,
  request serialization, stop/delete behavior, and existing RAG routing.
- 42 workflow/adapter/attachment/architecture tests, 22 backend tests, and
  34 frontend tests pass (98 total); scoped Ruff and `git diff --check` pass.
- An isolated LangGraph API 0.12.0 server with a deterministic fake model was
  exercised through the actual FastAPI route and HTTP thread API. First turn,
  follow-up recall, separate-thread isolation, failure recovery, stored history,
  and custom-only streaming all passed. The temporary server was stopped.
- Frontend production build passes. The deployed model and browser UI were not
  exercised; after rollout, send a name in Chat, ask for it in a follow-up,
  verify a new chat has no such context, and switch back to the original chat.
- Tauri `cargo check` is blocked by an existing cached permission path pointing
  at the absent `workflow-helper/frontend/src-tauri/target/...` directory.
- `npm audit --audit-level=moderate` reports two existing moderate advisories
  in `vitest`/`@vitest/mocker`; dependency versions were not changed.

Focused checks, from `agents/`:

```bash
.venv/bin/python -m pytest tests/unit/test_chat_graph.py tests/unit/test_chat_memory.py tests/unit/test_chat_attachments.py tests/unit/test_chat_integration.py tests/unit/test_rag_chat_graph.py tests/contract/test_langgraph_entries.py tests/contract/test_dependency_boundaries.py
```

From `backend/`, run `.venv/bin/python -m pytest tests/test_chat.py tests/test_rag_chat.py`.
From `frontend/`, run `npm test -- src/features/chat/chatRunner.test.ts src/shared/state/useChatStore.test.ts src/shared/api/agentServerClient.test.ts`
and `npm run build`.

The implementation follows Agent Server's
[thread streaming API](https://docs.langchain.com/langsmith/agent-server-api/thread-runs/create-run-stream-output)
and [managed checkpointing](https://docs.langchain.com/oss/python/langgraph/persistence).
