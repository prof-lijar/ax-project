# OpenAI-compatible LLM integration

Date: 2026-08-10

The `chat` LangGraph workflow uses the shared asynchronous adapter in
`ax-integrations` to call vLLM or another OpenAI-compatible
`/chat/completions` endpoint. The deterministic `agent` smoke graph remains
available without model credentials.

## Configuration

Copy `.env.example` to the ignored root `.env` and set the key locally:

```bash
cp .env.example .env
```

```dotenv
URL=http://192.168.0.17:8000/v1
MODEL=gemma-4-31b
OPENAI_API_KEY=your-bearer-token
```

`OPENAI_BASE_URL` may replace `URL`, and `OPENAI_MODEL` may replace `MODEL`.
The `OPENAI_*` names take precedence when both forms are set. `URL` may be a
server root, an `/v1` base URL, or the complete `/chat/completions` endpoint.

Do not put credentials in graph state, prompts, source files, command history,
or committed environment templates. Production deployments should inject the
key from their secret store.

## Run

Start the local Agent Server:

```bash
uv run langgraph dev --host 192.168.0.18 --port 2024 --no-browser
```

From this machine or another server on the same trusted network, invoke the
registered graph through its API:

```bash
curl -N http://192.168.0.18:2024/runs/stream \
  -H 'Content-Type: application/json' \
  -d '{
    "assistant_id": "chat",
    "input": {
      "message": "Explain how vLLM serves multiple users concurrently. Give a detailed explanation."
    },
    "stream_mode": "values"
  }'
```

The development server uses noop authentication. Do not expose port 2024 to an
untrusted network; production clients must use the authenticated gateway.

The workflow currently represents one chat turn: input is `message`, and the
terminal state adds `response`. The model adapter requests streamed SSE output
from vLLM and accumulates it for the graph state.

## Runtime behavior

- One process-wide async client reuses bounded HTTP connections.
- Requests use a 120-second timeout and at most three attempts.
- HTTP 429, HTTP 5xx, timeout, and transport failures are retryable only before
  response content has been emitted; partial generations are not replayed.
- Authentication failures and malformed provider events are permanent.
- Provider errors expose status and retryability without including the key or
  response body.

Tests use an in-memory HTTP transport and a fake chat model, so the normal test
suite does not require network access or credentials. A live readiness check
should be run from the deployment network before release.
