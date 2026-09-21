# Persistent AX chat history

Date: 2026-09-21

## Implemented behavior

AX conversations belong to the authenticated user and survive page reloads and
subsequent sign-ins. `/chat/{uuid}` supports reopening and browser navigation.
The existing sidebar now lists saved chats, supports rename and confirmed
deletion, and loads more results in 30-item pages. Transcripts initially load
50 messages, with older messages available without losing the reading position.
Titles use the first prompt (48 characters); manual titles permit 120 characters.
Reading or renaming does not change message-activity ordering.

Original attachments can be downloaded and explicitly reused in the same chat.
New and reused files share the existing five-file, 10 MiB/file, 25 MiB/turn and
100,000-character extracted-document limits. File bytes are not automatically
included in subsequent prompts. Unsaved drafts and pending browser File objects
remain ephemeral. RAG stays one-turn and session-only; changing between AX and
RAG after a conversation starts creates/selects a separate conversation.

## Architecture and security

Alembic revision `20260921_04` adds `chat.conversations`, `chat.messages`,
`chat.runs`, `chat.attachments`, and `chat.message_attachments`. The existing
`auth.alembic_version` remains the migration authority. Explicit cross-schema
foreign keys reference `auth.users`. After the historical auth migration,
the migration runner uses the neutral public search path so schema reflection
preserves qualified foreign keys. Historical public/auth upgrades remain supported.

`ChatStore` is the durable product boundary. User messages, assistant placeholders
and queued runs commit atomically before HTTP 202. The authenticated account,
never a client user ID, determines ownership. Another user's resource returns
404, including for administrators. Existing cookie, Origin and CSRF checks apply.
SSE subscriptions recheck authentication every five seconds and use private,
non-cacheable responses. No public raw thread or file-path API is introduced.

The `chat-worker` process claims PostgreSQL queue rows with SKIP LOCKED and
60-second leases. Four executions per worker are admitted by default. Heartbeats
check cancellation every second. Database uniqueness enforces one active reply
per conversation and one request per owner/deployment/idempotency key. Reusing
a key with different input returns 409. Late writes require the current, unexpired
lease and cannot revive terminal or deleted records.

The worker supplies the AX graph with at most 20 successful previous pairs and
32,000 historical characters loaded from the product database. It invokes
Agent Server's stateless `/runs/stream` with custom events and temporary-thread
deletion. The graph and its existing context limits are unchanged. Product
conversation IDs are no longer Agent Server thread IDs. History therefore remains
usable after development Agent Server checkpoints disappear.

The worker records cumulative output at most four times per second and commits
terminal output immediately. The browser observes revisioned snapshots through
SSE (database reads every 500 ms), including the latest snapshot on reconnect.
Closing the browser, navigating elsewhere, or logging out detaches the viewer
without cancelling AX generation. Explicit Stop persists cancellation and retains
partial output. There is a configurable 300-second execution deadline.

Queued work survives worker restarts. A lost running worker becomes `interrupted`
after its lease expires and maintenance runs (normally within 75 seconds).
Persisted partial text remains visible. Provider failure or malformed/incomplete
SSE becomes `failed`. Neither case automatically repeats model generation; users
can reuse their prompt. Full transcripts remain stored even when model context
excludes older, failed or stopped pairs.

`FileVault` stores originals and normalized copies on a separate private volume,
using UUID directories, checksums, private permissions, no-follow reads and fsync
before the database references them. The worker copies selected normalized files
to the existing staging volume. Agent Server can read staging but cannot access
the durable originals. Download responses force attachment disposition.

Delete immediately hides the chat and denies reads/downloads. Maintenance cancels
outstanding work and removes its files and records after active execution ends.
Old unreferenced upload directories are removed after one hour. Maintenance retries
failures. Backups retain their own retention policy; this is not a backup-erasure API.

Development and production currently share the account database. Compose sets
`AX_CHAT_DEPLOYMENT=development` or `production`; owners, lists, idempotency and
worker claims are scoped to that namespace. Each stack has separate file/staging
volumes. Do not change the namespace after rollout without a deliberate migration.

## HTTP interface

All paths below have prefix `/api/chat`:

| Path | Methods and purpose |
| --- | --- |
| `/conversations` | GET cursor-paginated summaries; POST multipart first prompt/files |
| `/conversations/{id}` | GET metadata, PATCH `{title}`, DELETE |
| `/conversations/{id}/messages` | GET paginated messages; POST multipart prompt/files/repeated `attachment_ids` |
| `/conversations/{id}/attachments` | GET cursor-paginated files eligible for reuse |
| `/attachments/{id}/download` | GET original bytes |
| `/runs/{id}` | GET run status and assistant snapshot |
| `/runs/{id}/events` | GET SSE `snapshot` events with revision IDs |
| `/runs/{id}/cancel` | POST idempotent cancellation |

New submissions require `Idempotency-Key` (1–128 characters) and return 202 with
`conversation_id`, `user_message_id`, `assistant_message_id`, and `run_id`.
Page envelopes are `{items,next_cursor}`; messages are ascending within each page.
Public APIs accept prompt/file selections, never caller-authored historical messages.

`POST /stream` remains a compatibility adapter producing `metadata`, custom
`response_delta`/`response_complete`, and safe error events. A supplied `session_id`
must identify an owned product conversation. Unknown legacy thread IDs return 404;
requests without an ID create a new saved conversation. Existing memory-only chats
are not imported. Refresh clients as part of the coordinated rollout.

## Configuration and operations

- `NEXGENT_DATABASE_URL`: existing application PostgreSQL connection.
- `AX_CHAT_DEPLOYMENT`: identical on API/worker; distinct across deployments sharing a DB.
- `AX_CHAT_FILE_ROOT`: durable originals/normalized files, `/var/lib/nexgent/chat-files` in Compose.
- `AX_CHAT_ARTIFACT_ROOT`: per-run staging, `/run/ax-chat` in Compose.
- `AX_CHAT_WORKER_CONCURRENCY`: defaults to 4, bounded to 1–32.
- `AX_CHAT_RUN_TIMEOUT_SECONDS`: defaults to 300.

Host development must explicitly choose a durable `AX_CHAT_FILE_ROOT`; the fallback
under `/tmp` is only suitable for disposable local testing. API and worker must share
the same paths and storage. The model/vision settings are unchanged.

From `nexgent/`, after backing up the application DB and existing volumes:

```bash
docker compose up --build -d backend chat-worker frontend
# Stable server instead:
docker compose -f compose.prod.yaml up --build -d backend chat-worker frontend
```

Backend startup runs the additive migration and checks chat schema readiness.
Worker startup depends on backend and Agent Server health. Run the API and worker
with the same filesystem user so their private staging directories remain readable.
For host development, load environment settings, run `uv run alembic upgrade head`,
then run `uv run uvicorn app.main:app` and `uv run python -m app.chat.worker` separately.

Back up both the database and the stack's `chat_files` volume. Coordinate snapshots
with submission/worker writes, or stop API/worker during the backup, to avoid dangling
file references. Do not use `docker compose down -v` for routine deployment.
Rollback application images without dropping the new tables or volume. An older
frontend cannot resume saved chats; preserve data and redeploy the matching version.

Inspect `docker compose logs chat-worker` for content-free run starts, completion,
failures and queue errors. Database run statuses distinguish queued, running,
completed, stopped, failed and interrupted. Database outages do not acknowledge
unsaved submissions. The worker retries queue access and recovers expired leases.
No automatic retention limit, storage quota UI, search, archive, shared chat,
message editing/branching, or cross-chat personal memory is included.

## Validation and remaining rollout check

The complete backend suite passed: 112 tests against an isolated PostgreSQL 18
cluster. Coverage includes fresh/historical migrations,
schema reflection, user/deployment isolation, idempotency, concurrent first-message
submission, pagination, file download/reuse, cancellation, lease expiry, deletion
and rejection of late writes. SQLite-backed regressions also run without PostgreSQL.
The worker tests require a valid completion event before marking a reply complete.

The actual browser/API/worker/PostgreSQL flow passed with a deterministic test
upstream: reload, original-byte download, file reuse, rename, close/reopen during
generation, another account's denial, explicit Stop, deletion, and narrow/desktop
rendering. The upstream did not send prompts to a real model. The frontend unit suite,
production build, 273 frontend tests, isolated Tauri `cargo check`, npm audit (zero vulnerabilities),
Compose validation, scoped Ruff, and whitespace checks were also exercised.

Reproduction commands:

```bash
# backend; point only at an isolated disposable PostgreSQL maintenance database
NEXGENT_TEST_DATABASE_URL=postgresql+psycopg://... .venv/bin/python -m pytest -q
# frontend
npm test
npm run build
CARGO_TARGET_DIR=/tmp/nexgent-cargo-chat-history cargo check --offline --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
```

For the browser fixture, set `NEXGENT_TEST_DATABASE_URL` to a disposable empty
PostgreSQL database, and set `NEXGENT_DATABASE_URL` to the same value for the worker.
Set both API and worker to `AX_CHAT_DEPLOYMENT=browser-smoke`, private temporary
file/staging roots, and `AX_AGENT_SERVER_URL=http://127.0.0.1:58172`. In separate
terminals from `backend/` run:

```bash
.venv/bin/python -m uvicorn chat_smoke_server:backend --factory --app-dir tests --host 127.0.0.1 --port 58171
.venv/bin/python -m uvicorn chat_smoke_server:agent --app-dir tests --host 127.0.0.1 --port 58172
.venv/bin/python -m app.chat.worker
```

From `frontend/`, run `NEXGENT_BACKEND_TARGET=http://127.0.0.1:58171 npm run dev -- --host 127.0.0.1 --port 58173`,
then `node scripts/saved-chat-ui-smoke.mjs`. Playwright must be installed separately;
`PLAYWRIGHT_MODULE` and `PLAYWRIGHT_BROWSERS_PATH` can point to an existing installation.
The fixture creates only test accounts in the explicitly selected test database.

No live development/production migration or service rollout was performed. The
remaining deployment verification is to run the Compose rollout command above,
sign in, attach a file, send an AX prompt, reload during generation, reopen from a
second browser, and ask a follow-up with that saved file selected. Confirm actual
model/vision capability and filesystem mounts in that environment.
