# Sumin

Sumin archives Slack channel uploads in Nextcloud and replies to mentions with
matching Nextcloud file URLs. Runtime configuration comes from the **agents
folder's `.env`**, using the `SUMIN_*` keys in `.env.example`. Credentials and
channel IDs can be supplied later; empty required settings fail at startup.

## Behavior and agent contract

- **Owner:** Sumin owns collection and file discovery for one configured Slack
  workspace and an explicit channel allowlist. Its worker runs a deterministic
  LangGraph; no model or supervisor is needed for this workflow.
- **Input:** signed Slack `file_shared`, channel messages containing `files`,
  and `app_mention` events. Message events preserve upload text and thread IDs.
  DMs, other workspaces/channels, message edits, and bot messages are ignored.
- **Output:** `<root>/<team-id>/<channel-name>/<slack-file-id>--<filename>`.
  Missing folders are created. The original channel folder and file paths are
  stored in PostgreSQL, so renames do not fragment existing archives.
- **Context:** `.sumin-context/<file-id>/<event-id>.json` beside the files keeps
  the original upload text, uploader, workspace/channel/file/event IDs, message
  timestamp and parent thread timestamp. Full conversation history is not read.
- **Search:** mention Sumin with a filename or upload-message keyword, such as
  `@Sumin find "budget.xlsx"` or `@Sumin 예산 파일 찾아줘`. Matching is
  case-insensitive keyword retrieval over live Nextcloud filenames and indexed
  upload text. Quoted text is an exact substring. Return at most ten matches in
  the originating thread. Search stays within that channel's folder, excludes
  context sidecars, and never returns a stale database-only file URL.
- **Authority:** read allowlisted Slack channels/files, create archive folders,
  conditionally upload immutable files/context, and reply to mentions in those
  same channels. Sumin does not create public shares or manage Nextcloud ACLs.
- **Stop/escalation:** one task per file or mention, one task at a time per
  worker, 300-second processing deadline, five attempts with durable backoff.
  Exhausted work is `failed`; the operator inspects and explicitly retries it.
  Files default to 25 MiB maximum. Unsupported remote/link-only Slack files,
  changed bytes at an existing archive path, and unavailable files fail visibly
  in the queue instead of becoming successful archives.

## Configure and start

Run from `agents/`. Fill these existing placeholder keys in `.env`:

| Key | Value |
| --- | --- |
| `SUMIN_SLACK_TEAM_ID` | Workspace ID (`T…`) |
| `SUMIN_SLACK_BOT_USER_ID` | Sumin bot user ID (`U…`) |
| `SUMIN_SLACK_CHANNEL_IDS` | Comma-separated approved channel IDs (`C…`/`G…`) |
| `SUMIN_SLACK_BOT_TOKEN` | Bot OAuth token (`xoxb-…`) |
| `SUMIN_SLACK_SIGNING_SECRET` | Slack app signing secret |
| `SUMIN_DATABASE_DSN` | Dedicated PostgreSQL database/role reachable by API and worker |
| `SUMIN_NEXTCLOUD_URL` | HTTPS installation base, e.g. `https://cloud.example/nextcloud` |
| `SUMIN_NEXTCLOUD_USER` | Dedicated archive account username |
| `SUMIN_NEXTCLOUD_PASSWORD` | Its Nextcloud app password |
| `SUMIN_NEXTCLOUD_ROOT` | Archive root folder, default `Slack` |
| `SUMIN_MAX_FILE_BYTES` | Maximum file bytes, default `26214400` |

The `SUMIN_*` namespace is independent of the existing weekly reporter's Slack
configuration. Existing `.env` settings are preserved. Native execution loads
`.env` explicitly; Compose passes the same file into both containers.

1. Create the Slack app from `config/sumin-slack-manifest.json`, replacing the
   callback host. Install it and invite Sumin to each approved channel. The
   scopes cover file reads, channel metadata/history, mentions, and replies;
   private channels need `groups:read` and `groups:history`.
2. Provide a PostgreSQL database and Nextcloud account. The migration command
   creates only the workflow-owned `sumin` schema/tables. Use a migration role
   for DDL; API/worker runtime needs table SELECT/INSERT/UPDATE, not database
   administration. With the supplied Compose file the configured role performs
   migration and runtime; production may apply migration separately.
3. Configure Nextcloud folder permissions for the intended channel audience.
   Returned `/index.php/f/<id>` URLs require the viewer's own Nextcloud access.
   Archiving does not automatically reproduce Slack membership or deletion rules.
4. Start the services and route a public HTTPS `/slack/events` endpoint to the
   loopback-bound API. Preserve the raw request body and Slack signature headers;
   cap ingress at 1 MiB and configure a body-read timeout at the reverse proxy.
   Only this signed callback needs to be publicly routed.

```bash
uv run --env-file .env python -m apps.sumin.manage migrate
uv run --env-file .env uvicorn apps.sumin.main:create_application --factory --host 127.0.0.1 --port 8093
# In another terminal:
uv run --env-file .env python -m apps.workers.sumin
```

Or use the opt-in standalone Compose file (it uses the configured external
PostgreSQL; it does not start a database or modify existing running stacks):

```bash
docker compose --env-file .env -f compose.sumin.yaml up -d --build
```

The API exposes `/healthz` and database-backed `/readyz`. The worker exposes no
HTTP port. The graph factory is worker-injected and is deliberately absent from
`langgraph.json`: Slack-authorized side effects must not be invoked through the
generic Chat run endpoint. To stop, use the same Compose file with `down`.

## Recovery and operational limits

The ingress verifies Slack's signing secret and five-minute timestamp window,
normalizes tasks, then commits the whole event to PostgreSQL before ACK. Slack
retries deduplicate by workspace/event/file identity. Database failure returns
503 so delivery can retry. HTTP ACK never means the archive is already done.

Workers claim tasks with `FOR UPDATE SKIP LOCKED`, a unique lease token, and a
360-second lease. Processing has a shorter 300-second deadline. Cancellation
leaves the lease for recovery; expired leases are reclaimed by another worker.
Stale completion tokens cannot acknowledge a new claim. Five unsuccessful or
interrupted attempts stop automatic work. Retry delays are 20, 40, 80, then
160 seconds. Logs carry event keys, attempt counts, and safe error codes only. The worker
disables inherited LangSmith tracing and HTTP request logging to avoid
exporting upload text or filenames.

Uploads use `If-None-Match: *`; an existing destination must contain identical
bytes. An interrupted file/context upload can therefore be replayed. Files with
the same human filename retain distinct Slack-ID prefixes. Reusing an old
channel name for a new channel fails on the unique folder mapping, requiring
operator reconciliation rather than combining two channels' data.

Slack reply delivery is at least once: a crash after Slack accepts a message
but before the queue commit can produce a repeated reply. It cannot cause a
new archive filename. Nextcloud listings are capped at 4 MiB; oversized
listings fail rather than silently presenting incomplete results. Downloads
accept only HTTPS `files.slack.com` URLs and refuse redirects. A Slack deployment
using a different download origin needs an explicitly reviewed adapter extension.

Inspect recent task status and retry one failed event after fixing the cause:

```bash
uv run --env-file .env python -m apps.sumin.manage status
uv run --env-file .env python -m apps.sumin.manage retry 'T123:Ev123:F123'
```

The database retains normalized events and upload-text metadata for replay and
search; Nextcloud owns file bytes and context JSON. Back up both. There is no
historical channel backfill, content/OCR/semantic indexing, cross-channel
search, automatic deletion sync, automatic retention cleanup, or error-message
posting for collection failures. Operators monitor failed tasks with the status
command and worker logs. Changing the archive account/root after collection
requires a coordinated migration of mappings and objects.

## Acceptance and verification

Implemented acceptance criteria:

- Approved channel upload creates its named folder, file, and context.
- Retries preserve one immutable destination; interrupted context writes resume.
- Mention search returns live Nextcloud URLs in the source thread.
- Private-channel boundaries, request signatures, replay age, path traversal,
  download origin, file/listing sizes, and XML entity rejection are enforced.
- Queue failures are visible, retries are bounded, and expired work is reclaimable.

```bash
uv run pytest tests/unit/test_sumin.py tests/unit/test_slack_integration.py tests/contract/test_dependency_boundaries.py
# Requires a disposable PostgreSQL database whose name contains "test":
SUMIN_TEST_DATABASE_DSN=... uv run pytest tests/integration/test_sumin_store.py
```

Offline tests exercise the graph through a partial upload, replay, contextual
search, and deleted-file case, plus adapter and ingress boundaries. The opt-in
PostgreSQL test covers concurrent duplicate enqueue, exclusive claims, expiry,
stale-token fencing, bounded retry exhaustion, path stability, and context
isolation. Live Slack/Nextcloud delivery and PostgreSQL/container execution
remain rollout gates until credentials and a test database are supplied.

API references: [Slack file events](https://docs.slack.dev/reference/events/file_shared/),
[message file payloads](https://docs.slack.dev/reference/events/message/file_share/),
[request verification](https://api.slack.com/docs/verifying-requests-from-slack),
and [Nextcloud WebDAV operations](https://docs.nextcloud.com/server/stable/developer_manual/client_apis/WebDAV/basic.html).

Validation checkpoint (2026-09-14): the focused suite passed **56 tests** with
**one PostgreSQL integration test skipped** because `SUMIN_TEST_DATABASE_DSN`
was unset. Ruff passed for every changed Python file; Compose configuration and
`git diff --check` passed. Repository-wide Ruff additionally reports two
pre-existing issues in `ax_integrations/__init__.py` (`__all__` ordering) and
`tests/unit/test_rag_chat_graph.py` (import ordering); those files are unchanged.
Docker database tests could not run because this account has no Docker access.
