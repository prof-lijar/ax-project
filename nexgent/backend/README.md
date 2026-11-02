# Nexgent Backend

FastAPI backend for AX Chat, Nextcloud, and durable Slack notifications.

## Private file storage

`/api/file-storage` provides per-user browsing/search, file upload/download,
folders, rename, move, recursive copy, trash, restore, and permanent deletion.
PostgreSQL owns the logical filesystem; immutable contents live in the private
Nextcloud `Nexgent/FileStorage/` directory. The shared Nextcloud browser hides and
blocks that reserved directory. Requests use the existing session and CSRF protection.

Run `uv run alembic upgrade head` before starting the API. Schedule
`uv run python -m app.file_storage.maintenance --limit 100` periodically with the
same environment to reclaim purged files and abandoned uploads. Configure limits
and deployment isolation using the `FILE_STORAGE_*` settings in `example.env`.
See [File storage service](../docs/08-implementation/file-storage-service.md)
for the API contract, consistency behavior, validation, and rollout checks.

## Slack notifications

`POST /api/notifications/slack` queues a notification and returns `202` with a
job ID; `GET /api/notifications/{id}` reports delivery status.
`GET /api/notifications/capabilities` lists configured destination aliases.
Requests use the existing browser session/CSRF protection or a server-side
notification service Bearer token. Submission requires `Idempotency-Key`.

Configuration is optional and disabled by default. Add the `NEXGENT_SLACK_*`
and `NEXGENT_NOTIFICATION_*` values from `example.env` when ready. Run migrations
and start the delivery worker alongside the API:

```bash
uv run alembic upgrade head
uv run python -m app.notifications.worker
```

The development and production Compose stacks include `notification-worker`.
See [Slack notification service](../docs/08-implementation/slack-notification-service.md)
for configuration, browser/agent examples, retry behavior, scaling, and rollout.

## Get Started

Install dependencies:

```bash
uv sync --extra dev
```

Create your local environment file:

```bash
cp example.env dev.env
```

Edit `dev.env` and set your Nextcloud app password:

```bash
NC_PASS=your-nextcloud-app-password
```

For a local Nextcloud server using a self-signed certificate, either trust its CA:

```bash
NC_CA_BUNDLE=/path/to/nextcloud-ca.pem
```

Or, for local development only, disable verification:

```bash
NC_VERIFY_SSL=false
```

Load environment variables:

```bash
set -a
source dev.env
set +a
```

Run the server for local access only:

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

AX Chat also requires an independent worker, started in a second terminal with
the same database, deployment, file-root, and Agent Server settings:

```bash
uv run python -m app.chat.worker
```

The Compose stacks start this worker automatically. See
[Persistent AX chat history](../docs/08-implementation/persistent-ax-chat-history.md)
for storage, endpoints, rollout, backup, recovery, and browser verification.

Open:

```text
http://127.0.0.1:8000/docs
```

Run the server for access from another PC on the same network:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open from another PC, replacing the IP address with this server's LAN IP:

```text
http://192.168.0.18:8000/docs
```

If the browser or `curl` times out from another PC, allow inbound TCP traffic on port `8000`:

```bash
sudo ufw allow from 192.168.0.0/24 to any port 8000 proto tcp
sudo ufw reload
sudo ufw status verbose
```

## Test

```bash
uv run pytest
```

## AX Chat file attachments

`POST /api/chat/stream` accepts `multipart/form-data` with a required `prompt`
field and up to five repeated `files` fields. This compatibility endpoint now
submits durable work and streams saved output; disconnecting does not cancel it.
New clients use `POST /api/chat/conversations` and
`POST /api/chat/conversations/{id}/messages` with an `Idempotency-Key` header.
All requests require the existing authenticated cookie, Origin, and CSRF token.
Supported attachments are embedded-text PDF,
UTF-8 TXT/Markdown/CSV, DOCX paragraphs and tables, and PNG/JPEG/WebP images.
Each file is limited to 50 MiB, the request is limited to 50 MiB, and extracted
document text is limited to 100,000 characters.

The backend retains original and normalized files in `AX_CHAT_FILE_ROOT`, a
private persistent volume shared only with the worker. Users can download the
originals and explicitly select saved attachment IDs on follow-up messages.
The worker stages normalized files into a private transient directory for each
run. Backend, worker and Agent Server mount the same staging volume at
`AX_CHAT_ARTIFACT_ROOT` (`/run/ax-chat` in the image), writable by the backend
and read-only for Agent Server. Staging files are deleted after the worker run
completes, fails, or is cancelled; durable files remain until chat deletion.
Staging directories left by a process crash
are removed on the next backend startup after `AX_CHAT_STALE_AFTER_SECONDS`.

Example request (supply your own login cookie jar and current CSRF token):

```bash
curl --no-buffer http://127.0.0.1:8000/api/chat/stream \
  --cookie cookies.txt \
  --header 'Origin: http://localhost:5173' \
  --header 'X-CSRF-Token: YOUR_CSRF_TOKEN' \
  --form 'prompt=Summarize these files' \
  --form 'files=@notes.md;type=text/markdown' \
  --form 'files=@chart.png;type=image/png'
```

Validation errors use a stable JSON envelope:

```json
{
  "error": {
    "schema_version": "1",
    "code": "unsupported_file_type",
    "message": "Supported files are PDF, TXT, Markdown, CSV, DOCX, PNG, JPEG, and WebP.",
    "filename": "archive.zip"
  }
}
```

Native header, section, context, divider and table blocks are now supported.
See [native-block contracts and deployment](../docs/08-implementation/slack-notification-native-blocks.md).
