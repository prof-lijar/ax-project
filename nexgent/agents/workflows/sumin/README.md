# Sumin

Sumin archives Slack channel uploads in Nextcloud and replies to mentions with
matching Nextcloud file URLs. Runtime configuration comes from the **agents
folder's `.env`**, using `AGENT_DATABASE_DSN` and the `SUMIN_*` keys in `.env.example`. Credentials can be supplied later; empty required settings fail at startup.
The workspace and bot user IDs are discovered from the bot token. Invite Sumin
to an existing or future channel to enable it; no channel list is configured.

## Behavior and agent contract

- **Owner:** Sumin owns collection and file discovery for one configured Slack
  workspace and every public/private channel the bot has joined. Its worker runs a deterministic
  LangGraph; no model or supervisor is needed for this workflow.
- **Input:** authenticated Socket Mode `file_shared`, channel messages containing `files`,
  and `app_mention` events. Message events preserve upload text and thread IDs.
  DMs, group DMs, other workspaces, message edits, and bot messages are ignored.
  The worker checks current membership before accessing the channel archive.
- **Output:** `<root>/<channel-name>/<slack-file-id>--<filename>`.
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
- **Authority:** read joined Slack channels/files, create archive folders,
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
| `SUMIN_SLACK_BOT_TOKEN` | Bot OAuth token (`xoxb-…`) |
| `SUMIN_SLACK_APP_TOKEN` | App-level token (`xapp-…`) with `connections:write` |
| `SUMIN_SLACK_SIGNING_SECRET` | Only required for the optional HTTP adapter |
| `AGENT_DATABASE_DSN` | Shared PostgreSQL connection for agents, reachable by API and worker |
| `SUMIN_NEXTCLOUD_URL` | HTTPS installation base, e.g. `https://cloud.example/nextcloud` |
| `SUMIN_NEXTCLOUD_USER` | Dedicated archive account username |
| `SUMIN_NEXTCLOUD_PASSWORD` | Its Nextcloud app password |
| `SUMIN_NEXTCLOUD_VERIFY_SSL` | Default `true`; `false` disables Nextcloud certificate and hostname verification only |
| `SUMIN_NEXTCLOUD_CA_BUNDLE` | Optional trusted PEM CA/certificate file on the host |
| `SUMIN_NEXTCLOUD_ROOT` | Archive root folder, default `Slack` |
| `SUMIN_MAX_FILE_BYTES` | Maximum file bytes, default `26214400` |

The shared `AGENT_DATABASE_DSN` is used by Sumin’s event listener, worker, and management
commands. The former `SUMIN_DATABASE_DSN` is no longer read.
The `SUMIN_*` namespace is independent of the existing weekly reporter's Slack
configuration. The retired `SUMIN_SLACK_TEAM_ID`, `SUMIN_SLACK_BOT_USER_ID`, and
`SUMIN_SLACK_CHANNEL_IDS` settings are ignored and are no longer needed. Native execution loads
`.env` explicitly; Compose passes the same file into the listener and worker.

1. Create/update the Slack app using `config/sumin-slack-manifest.json`.
   In [your Slack app settings](https://api.slack.com/apps), enable **Socket Mode**.
   Under **Basic Information → App-Level Tokens**, generate a token with
   `connections:write` and put it in `SUMIN_SLACK_APP_TOKEN` in `agents/.env`.
   Keep the `xoxb-` bot token in `SUMIN_SLACK_BOT_TOKEN`; both must belong to the
   same app. Under **Event Subscriptions**, enable events and subscribe to
   `file_shared`, `message.channels`, `message.groups`, and `app_mention`.
   No Request URL is required in Socket Mode. Install/reinstall the app after
   scope changes, then invite it to each channel it should handle. Future
   invitations require no settings change or restart. Private channels need
   the manifest's `groups:read` and `groups:history` scopes.
2. Provide a PostgreSQL database and Nextcloud account. The migration command
   creates only the workflow-owned `sumin` schema/tables. Use a migration role
   for DDL; API/worker runtime needs table SELECT/INSERT/UPDATE, not database
   administration. With the supplied Compose file the configured role performs
   migration and runtime; production may apply migration separately.
3. Configure Nextcloud folder permissions for the intended channel audience.
   Returned `/index.php/f/<id>` URLs require the viewer's own Nextcloud access.
   Archiving does not automatically reproduce Slack membership or deletion rules.
4. Start the Socket Mode listener and worker. The listener connects outward to
   Slack; neither process needs a public endpoint or an inbound port.

```bash
uv run --env-file .env python -m apps.sumin.manage migrate
uv run --env-file .env python -m apps.sumin.socket
# In another terminal:
uv run --env-file .env python -m apps.workers.sumin
```

For the unified Docker deployment, run your normal command from **`nexgent/`**:

```bash
sudo docker compose up --build -d
```

The root Compose file includes Sumin automatically in the same `nexgent`
project: `sumin-migrate`, `sumin-events`, and `sumin-worker`. The event listener
and worker wait for a successful migration. No separate `-f` command or profile
is required. All Sumin settings stay in `agents/.env`, including the CA-file
path used for Compose interpolation.

The supplied deployment targets this Linux host and uses host networking so
`AGENT_DATABASE_DSN` can reach PostgreSQL published on `127.0.0.1:5433`.
No HTTP port is exposed. The reusable service definitions remain in
`agents/compose.sumin.yaml`, included by the root file. Normal root
`sudo docker compose down` stops Sumin along with the other services.

At startup, both event listener and worker call Slack `auth.test` with a 15-second overall
deadline and require a valid workspace, bot user, and bot ID. Discovery failure
stops startup; no guessed identity or environment override is used.
The listener logs `slack_socket_connected` after connecting and
`sumin_event_queued` after a durable enqueue. The graph factory is worker-injected
and absent from `langgraph.json`. The optional HTTP adapter remains available
for deployments that explicitly disable Socket Mode, configure the signing
secret, and provide a publicly reachable `/slack/events` URL; it is not started
by the supplied Compose file. Do not run both transport modes for one app.

## Recovery and operational limits

The Socket Mode connection authenticates with the app token. Normalization
restricts events to the bot token's discovered workspace and channel IDs, then
commits the whole event to PostgreSQL before acknowledging its socket envelope.
Slack retries deduplicate by workspace/event/file identity. Database failure,
invalid input, or overload leaves the envelope unacknowledged for Slack's
bounded delivery retries. An ACK means queued, not already archived. Events
missed while the listener is offline are not automatically backfilled.

The SDK receive queue is bounded to 128 messages, with at most four durable
ingress handlers. Each handler has a two-second persistence deadline and a
one-second ACK deadline. Initial socket connection is limited to 30 seconds;
a disconnected connection gets at most 60 seconds to recover before the
process exits for its supervisor to restart. Shutdown closes the socket and
cancels outstanding handlers; committed but unacknowledged tasks deduplicate
on replay. SDK transport logs are scrubbed because WebSocket URLs can contain
credentials. The HTTP adapter retains its signed-request verification.

Workers claim tasks with `FOR UPDATE SKIP LOCKED`, a unique lease token, and a
360-second lease. Processing has a shorter 300-second deadline. Cancellation
leaves the lease for recovery; expired leases are reclaimed by another worker.
Stale completion tokens cannot acknowledge a new claim. The worker calls
`conversations.info` before archive/search work; removal from the channel
blocks queued work. The outbound adapter repeats this check before every
reply, then scopes the existing Slack sender to that one destination without
changing other workflows’ static destination policy. Membership is never cached. Five unsuccessful or
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

- Joined channel upload creates its named folder, file, and context.
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


Membership update (2026-09-15): identity discovery and membership replace the
manual workspace/bot/channel configuration. Tests cover startup discovery and
failure, unresolved-identity ingress, new public/private channels, bot removal,
group-DM exclusion, and membership-checked replies. Existing database records
and archive paths retain their workspace/channel IDs; no migration is needed.

Identity reference: [Slack auth.test](https://docs.slack.dev/reference/methods/auth.test/).

Validation checkpoint (2026-09-15): 69 focused tests passed; the PostgreSQL
integration test was skipped without its test DSN. Changed-file Ruff, Compose
configuration, and whitespace checks passed. Live Slack calls were not made.


### Startup troubleshooting

Enable **Socket Mode** and **Event Subscriptions** in the Slack app, set the
`xapp-` token with `connections:write`, and check `sumin-events` logs for
`slack_socket_connected` and `sumin_event_queued`. If connected but no events
arrive, check the four bot-event subscriptions and the bot's channel membership.

Nextcloud certificate verification defaults to enabled. For a self-signed/private
certificate, obtain the trusted PEM certificate/CA from the Nextcloud operator
and set `SUMIN_NEXTCLOUD_CA_BUNDLE` to its host path. The Compose worker mounts
that file read-only; by default it mounts the host system CA bundle. Slack
uses its separate default TLS client, so Nextcloud trust changes do not affect
Slack. Set `SUMIN_NEXTCLOUD_VERIFY_SSL=false` in `agents/.env` to disable
verification for Nextcloud and ignore the CA bundle. The backend's
`NC_VERIFY_SSL` setting is not inherited by Sumin. Rebuild/recreate with
`sudo docker compose up --build -d` from `nexgent/` after changing settings.

```bash
# From nexgent/:
sudo docker compose ps -a sumin-migrate sumin-events sumin-worker
sudo docker compose logs --tail=100 sumin-migrate sumin-events sumin-worker
```

Read-only checks on 2026-09-15 confirmed a valid Slack bot token and a reachable
host PostgreSQL, but no `sumin.events` table or listener on port 8093. The
configured Nextcloud host presents a self-signed certificate not trusted by
the host CA store. The idempotent migration was subsequently applied successfully to the configured
agent database. Docker status/redeployment still requires an account with
socket access. The local Nginx certificate `/etc/nginx/ssl/nextcloud.crt` also
fails hostname verification for the Tailscale address (it names 192.168.0.18).
With verification enabled, it must be replaced with a certificate containing
the configured hostname in its Subject Alternative Name; merely trusting the
current certificate is not sufficient. Subsequently, at the operator's request,
the local `.env` was set to `SUMIN_NEXTCLOUD_VERIFY_SSL=false`.


Socket Mode reference: [Slack SDK configuration](https://docs.slack.dev/tools/python-slack-sdk/socket-mode/).


The installed bot token was checked on 2026-09-15 and lacked
`app_mentions:read`, `channels:read`, `files:read`, `groups:read`, and
`groups:history`. Add these under **OAuth & Permissions → Bot Token Scopes**
and reinstall the app, then update the bot token in `.env` if it changes.
`SUMIN_SLACK_APP_TOKEN` was still empty at this checkpoint. No Slack messages
were sent and no Nextcloud files were uploaded during the connectivity checks.


### Markdown and editable text uploads

Sumin accepts Slack `hosted` and `snippet` file modes, including `.md` files.
It downloads the full authenticated file bytes using `url_private_download`
or `url_private`, never the truncated snippet preview. File identity, channel
membership, download host, byte limits, and replay checks still apply. External
files, posts, and unknown modes remain unsupported.

Earlier versions accepted only `hosted`, causing editable text uploads with
`mode=snippet` to fail with `unsupported_slack_file`. Rebuild from `nexgent/`
using `sudo docker compose up --build -d`, then upload the file again. Pending
events will retry normally; terminal failed events require explicit retry via
`sudo docker compose exec sumin-worker uv run --no-sync python -m apps.sumin.manage retry '<event-key>'`.
Do not reset terminal events until the updated worker is deployed.

See [Slack file modes and authenticated download fields](https://docs.slack.dev/reference/objects/file-object/).


### Single-workspace channel folders

Sumin archives this workspace directly under `<root>/<channel-name>/`, for
example `Slack/nexgent-test/`. Workspace identity is still validated internally.
The startup migration removes the workspace-ID segment from existing channel
and file path mappings once, preserving custom roots and original channel names.
It does not move or delete Nextcloud files or reset completed events. This
rollout assumes the operator clears the old archive. Stop Sumin before clearing
Nextcloud, then rebuild from `nexgent/`:

```bash
sudo docker compose stop sumin-events sumin-worker
# Clear the old Nextcloud archive, then:
sudo docker compose up --build -d
```

Upload new files after startup. Completed events are not backfilled. Mapping
collisions fail the migration transaction rather than merge channel archives.
