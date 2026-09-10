# Chat File Attachments

Date: 2026-08-14

## Implemented Behavior

AX Chat accepts a required prompt with up to five transient attachments. Each
file is limited to 10 MiB and the combined request is limited to 25 MiB.
Supported documents are text-bearing PDF, TXT, Markdown, CSV, and DOCX;
supported images are PNG, JPEG, and WebP. Image-only or encrypted PDFs are
rejected, with scanned pages expected to be attached as images instead.

The React client sends `multipart/form-data` to
`POST /api/chat/stream` on the Nexgent FastAPI backend. The backend validates
and normalizes each upload, stores only request-scoped artifacts, and forwards
typed references to the private Agent Server. It relays the Agent Server SSE
stream without exposing the model endpoint or credentials. Disconnecting the
browser closes the upstream stream with `on_disconnect: cancel` and removes
the temporary files.

## Security and Architecture Decisions

- Original uploads are not persisted. Normalized files live under
  `AX_CHAT_ARTIFACT_ROOT` and are removed after success, failure, or
  cancellation; stale request directories are swept as a crash-recovery guard.
- Agent Server receives versioned attachment references containing a safe
  filename, kind, media type, file URI, byte size, and SHA-256 digest. Its
  reader confines access to the configured root, rejects links and traversal,
  and verifies the declared size and checksum.
- Attachment runs request only LangGraph `custom` stream mode and finish with a
  `response_complete` event, preventing initial-state values from echoing
  private file references. Text-only runs keep the prior values contract.
- Extracted document content is explicitly delimited and treated as untrusted
  user data. Binary content does not appear in graph state, SSE metadata, or
  logs.
- Image content is sent as OpenAI-compatible `image_url` parts only when
  `OPENAI_SUPPORTS_VISION=true`. The default is false and produces a safe,
  user-facing capability error.
- The Compose development stack shares a private `chat_attachments` volume
  read-write with the backend and read-only with Agent Server. This is the
  single-host development boundary; a multi-host deployment must replace it
  with a private object-store implementation.

## Configuration and Operation

The backend uses:

```dotenv
AX_AGENT_SERVER_URL=http://agent-server:2024
AX_CHAT_ARTIFACT_ROOT=/run/ax-chat
```

Agent Server uses the same artifact root and an explicit vision flag:

```dotenv
AX_CHAT_ARTIFACT_ROOT=/run/ax-chat
OPENAI_SUPPORTS_VISION=false
```

Enable vision only after a live image request succeeds against the configured
model. Start the integrated development stack from `nexgent/`:

```bash
docker compose up --build backend agent-server frontend
```

## Validation

The deterministic gates cover multipart request construction, supported and
rejected formats, size/count limits, document extraction, image normalization,
temporary cleanup, safe attachment reference resolution, checksum checking,
vision capability errors, provider payloads, SSE parsing, and cancellation.
Run:

```bash
cd agents && uv run ruff check apps workflows packages tests && uv run pytest -q
cd ../backend && uv run pytest
cd ../frontend && npm test && npm run build
docker compose config
```

Live release verification requires one text-document question and one image
question. Confirm incremental output, cancel a second request, and verify the
request directory is removed in all three cases.

## Known Limitations

- PDF support requires embedded text; OCR and scanned-PDF rendering are not
  included.
- DOCX embedded images and macros are ignored.
- Chat remains one-turn and session-only; attachments are unavailable to later
  messages.
- Malware scanning and durable attachment audit storage are not included in
  this transient local-development implementation.


## Update: Enable vision for the verified vLLM model

Date: 2026-09-10

The project-root `nexgent/.env` now sets `OPENAI_SUPPORTS_VISION=true`.
This file contains only the non-secret capability setting. Both development
and production Compose files interpolate it into the Agent Server environment;
that explicit environment entry overrides `agents/.env`. Shell environment
variables or an explicitly selected Compose environment file can override the
project-root default.

Validation:

- A direct authenticated request to the configured `gemma-4-31b` vLLM endpoint
  returned HTTP 200 and correctly described a generated PNG's red, green, blue,
  and yellow quadrants. The request used image_url content and
  `chat_template_kwargs: {"enable_thinking": false}`; no model credentials were
  printed or committed.
- Both `docker compose --env-file .env -f compose.yaml config --quiet` and
  `docker compose --env-file .env -f compose.prod.yaml config --quiet` exited 0.
  The restricted environment emitted stream-fd warnings. Parsed configuration
  output independently confirmed the Agent Server vision value is `true` in
  both stacks without printing other environment values.
- No frontend, backend API, or model-client code changed in this configuration
  update. The direct model probe does not establish full application upload
  success.

Apply to the development service from `nexgent/`:

```bash
docker compose up -d --no-deps --force-recreate agent-server
docker compose exec agent-server printenv OPENAI_SUPPORTS_VISION
```

For production, use `docker compose -f compose.prod.yaml` for both commands.
A plain restart does not load changed container environment values. Service
recreation was not performed as part of this commit task. Remaining verification:
run the commands above, confirm `true`, then upload a PNG with a description
question at `/chat` and verify the streamed answer. The direct probe's
thinking option was not added to the application request configuration.
