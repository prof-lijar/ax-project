# Nexgent Backend

FastAPI backend for AX Chat and Nextcloud integration.

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
Each file is limited to 10 MiB, the request is limited to 25 MiB, and extracted
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
