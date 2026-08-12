# Chat Response Streaming

Date: 2026-08-10

## Implemented

The `chat` workflow now forwards model text as it arrives instead of waiting
for `OpenAICompatibleChatModel.complete()` to aggregate the provider stream.
The workflow iterates the existing provider-neutral `stream()` interface,
emits each non-empty text chunk through LangGraph custom events, and assembles
the same chunks into the final `response` state value.

The workflow allows up to 2,048 generated tokens per response. This replaces
the initial 500-token limit so detailed explanations and structured Markdown
answers can complete while keeping generation time and resource use bounded.

The public Agent Server stream contract is:

```json
{
  "assistant_id": "chat",
  "input": { "message": "<current user message>" },
  "stream_mode": ["custom", "values"],
  "on_disconnect": "cancel"
}
```

Custom SSE events contain only safe text deltas:

```text
event: custom
data: {"response_delta":"Hello"}
```

The terminal values event retains the complete response:

```text
event: values
data: {"message":"...","response":"Hello world"}
```

Clients concatenate `response_delta` fields for immediate display and use the
final `values.response` as the authoritative completed output. Empty provider
responses remain errors. Agent Server normally continues a run when its stream
client disconnects, so the explicit `on_disconnect` policy is required. It
cancels the run when the UI aborts the stream, allowing async cancellation to
close the graph's active provider HTTP stream.

## Security and Decisions

- The provider URL, model identifier, and `OPENAI_API_KEY` remain environment
  settings owned by the Agent Server integration layer.
- The browser connects only to Agent Server and receives text deltas; it never
  receives provider authorization headers or raw provider SSE envelopes.
- The existing provider retry rule remains unchanged: retries are allowed only
  before any content has been emitted, preventing duplicated partial output.
- The graph remains stateless per request and does not accept transcript history.

## Validation

Run from `agents/`:

```bash
uv run ruff check workflows tests
uv run pytest -q tests/unit/test_chat_graph.py tests/unit/test_chat_integration.py
```

Full Ruff validation and all 26 agent tests passed. The graph regression test
verifies ordered custom deltas and the matching final values response.
Integration tests continue to verify provider SSE parsing, authorization
isolation, request shape, bounded retries, and empty/failure behavior.

Rebuild the containerized Agent Server after this change:

```bash
cd ..
sudo docker compose up --build -d agent-server frontend
sudo docker compose logs -f agent-server frontend
```

Live verification should confirm several `event: custom` records arrive before
the terminal `event: values` record and that the frontend updates one assistant
message incrementally.
