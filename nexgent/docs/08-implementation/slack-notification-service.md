# Slack notification service

Date: 2026-09-29 (Asia/Seoul)

## Implementation

The backend exposes reusable notification submission and status APIs. A request
persists a job in PostgreSQL and returns immediately with `202 Accepted`;
an independent asynchronous worker delivers the message. Browser navigation,
API restarts, and caller disconnects do not cancel an accepted notification.
No extra broker or Python dependency is required.

Code lives in `backend/app/notifications/`: configuration, validated schemas,
submission service, transactional store, Slack adapter, routes, and worker.
Migration `20260929_05` adds `notifications.notification_jobs` and
`notifications.notification_rate_gates`; auth and chat tables are preserved.

The integration uses Slack's bot-token `chat.postMessage` API. Create/install a
Slack app with `chat:write`, and invite the bot to each configured channel.
Only server-configured channel aliases are accepted. Callers cannot supply
credentials, webhook URLs, arbitrary channel IDs, or raw Block Kit payloads.

Messages support a title, severity, body, up to ten name/value fields, a detail
link, and an optional Slack thread timestamp. The adapter creates Block Kit
sections and a screen-reader/notification fallback. Plain-text blocks and
escaped fallback text keep agent-generated mentions literal. Link/media unfurls
are disabled. This foundation sends messages; it does not receive Slack events
or register interactive callbacks.

References: [chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/)
and [Slack rate limits](https://docs.slack.dev/apis/web-api/rate-limits/).

## Configuration

Add these to `backend/dev.env` or `backend/prod.env` when ready. The existing
files and their secrets were not changed. `backend/example.env` contains the
new placeholders.

```dotenv
NEXGENT_SLACK_ENABLED=true
NEXGENT_SLACK_BOT_TOKEN=xoxb-REPLACE_WITH_BOT_TOKEN
NEXGENT_SLACK_CHANNELS='{"default":"C0123456789","alerts":"C0987654321"}'
NEXGENT_NOTIFICATION_SERVICE_TOKEN=REPLACE_WITH_AT_LEAST_32_RANDOM_CHARACTERS
```

Generate a service token with `openssl rand -hex 32`. It is a Nexgent API
credential, separate from the Slack bot token. Keep both tokens server-side.
The service token is optional when only browser sessions submit notifications.

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXGENT_SLACK_ENABLED` | `false` | Enables submission and worker delivery. |
| `NEXGENT_SLACK_BOT_TOKEN` | empty | Slack bot credential; required when enabled. |
| `NEXGENT_SLACK_CHANNELS` | `{}` | JSON object mapping aliases to channel IDs; required when enabled. |
| `NEXGENT_NOTIFICATION_SERVICE_TOKEN` | empty | Optional 32–512 character Bearer token for trusted services. |
| `NEXGENT_NOTIFICATION_DEPLOYMENT` | `AX_CHAT_DEPLOYMENT`, else `default` | Queue/ownership/rate-limit namespace. |
| `NEXGENT_NOTIFICATION_CONCURRENCY` | `4` | Concurrent deliveries per worker, range 1–32. |
| `NEXGENT_NOTIFICATION_MAX_ATTEMPTS` | `5` | Total attempts per job, range 1–10. |
| `NEXGENT_NOTIFICATION_POLL_SECONDS` | `1` | Idle polling interval, range 0.1–30 seconds. |
| `NEXGENT_SLACK_TIMEOUT_SECONDS` | `10` | Total Slack request deadline, range 1–60 seconds. |

API and worker settings must agree. Destination aliases match
`[a-z][a-z0-9_-]{0,63}`. Channel IDs start with `C` or `G`. If `default` is not
configured, callers must supply another configured alias. Disabled installations
start normally, expose `enabled: false`, and reject submissions with
`503 notifications_disabled`. The disabled worker waits without connecting to
Slack or opening a database connection. Restart API and workers after changing
configuration; settings are read at process startup.

## API contract

| Method and path | Result |
| --- | --- |
| `GET /api/notifications/capabilities` | Enabled flag and configured destination aliases. This is configuration discovery, not worker health. |
| `POST /api/notifications/slack` | Accepts JSON and a required `Idempotency-Key`; returns `202` and a `Location` status URL. |
| `GET /api/notifications/{id}` | Returns the submitting caller's job status; other owners receive `404`. |

Example submission:

```json
{
  "destination": "alerts",
  "title": "Weekly report complete",
  "text": "The weekly report is ready to review.",
  "severity": "success",
  "fields": [{"name": "Reports", "value": "12"}],
  "url": "https://nexgent.example/reports/42"
}
```

Only `text` is required (1–4000 characters). `destination` defaults to
`default`; `severity` defaults to `info` and also allows `success`, `warning`,
and `error`. Title length is at most 150; field name/value limits are 100/1000.
URLs must be HTTP(S), at most 2000 characters, and contain no credentials.
`thread_ts`, when supplied, is a Slack timestamp such as `1234567890.123456`.
Unknown properties are rejected.

Responses contain `id`, `provider: "slack"`, `destination`, `status`,
`attempts`, UTC `created_at`, `updated_at`, optional `sent_at`, `error_code`,
and `slack_ts`. They do not return stored message bodies or credentials.
States are `queued` → `sending` → `sent` or `failed`; retryable failures
transition back to `queued`. `202` confirms persistence, not Slack delivery.

The idempotency key is 1–128 visible ASCII characters, scoped to deployment
and caller. Reusing it with the same normalized payload returns the existing
job, including a terminal job. A different payload returns
`409 idempotency_conflict`. Use one stable key for retries of one logical event.
A new logical event, or an intentional resend of a failed job, needs a new key.

Other errors follow the backend's `{"error":{"code":"..."}}` envelope:
`401` for absent/invalid authentication, `403` for failed browser Origin/CSRF,
`422` for invalid input or an unknown destination, and `503` for disabled
notifications or unavailable database access. The existing database handler
uses `account_unavailable` for database failures across backend features.

## Frontend and agent integration

Any authenticated browser user can submit. Use the existing same-origin
backend proxy, login cookie, and CSRF token from `/api/me`. No new cross-origin
policy is introduced. A separate frontend origin must be integrated with the
existing login/proxy policy before using browser cookies.

```javascript
const me = await fetch('/api/me', { credentials: 'include' }).then(r => r.json());
const eventKey = crypto.randomUUID(); // Keep this value if retrying this event.
const response = await fetch('/api/notifications/slack', {
  method: 'POST',
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRF-Token': me.csrf_token,
    'Idempotency-Key': eventKey,
  },
  body: JSON.stringify({ text: 'Report ready', severity: 'success' }),
});
if (!response.ok) throw new Error(`Notification submission failed: ${response.status}`);
const job = await response.json();
// Poll this URL until status is sent or failed; apply a bounded polling policy.
const statusUrl = `/api/notifications/${job.id}`;
```

Trusted agents/services use the separate notification Bearer token. It grants
access only to the three notification operations above and does not authorize
account, chat, admin, Nextcloud, or other integration endpoints. Bearer requests
do not need browser cookies, Origin, or CSRF headers. All callers using the
shared token share the `service:notifications` owner; namespace their event
keys (for example `weekly-report:42:complete`). The token is not per-agent RBAC.

```bash
curl --fail-with-body http://127.0.0.1:8000/api/notifications/slack \
  --header "Authorization: Bearer $NEXGENT_NOTIFICATION_SERVICE_TOKEN" \
  --header 'Content-Type: application/json' \
  --header 'Idempotency-Key: weekly-report:42:complete' \
  --data '{"destination":"default","text":"Report ready","severity":"success"}'

curl --fail-with-body http://127.0.0.1:8000/api/notifications/REPLACE_WITH_JOB_ID \
  --header "Authorization: Bearer $NEXGENT_NOTIFICATION_SERVICE_TOKEN"
```

Backend code can reuse the synchronous `NotificationService.submit(owner,
SlackNotification(...), request_key)` with a `NotificationStore(engine,
settings.deployment)`. It performs the same configuration, destination, and
idempotency checks as the API. Call it in a thread pool from async code. Pass a
trusted, stable owner identity; external callers must go through the API.

## Delivery and scaling

Workers use short PostgreSQL transactions and `FOR UPDATE SKIP LOCKED` claims.
Network delivery happens outside database transactions using a pooled async
HTTP client. Shared gates serialize deliveries to each channel, leave at least
one second between completed attempts, and apply Slack `Retry-After` pauses
across the configured workspace. Replicas can concurrently deliver to different
channels. Increasing concurrency cannot increase Slack's per-channel limit.

Transport failures, timeouts, HTTP 408/5xx, temporary Slack errors, and rate
limits retry with bounded exponential backoff and jitter; valid `Retry-After`
values take priority. Invalid credentials, missing scopes, unavailable channels,
and rejected payloads fail without retry. Only sanitized error codes are stored
and logged. Exhausted jobs remain inspectable. No automatic terminal-job replay
or payload retention/purge policy is implemented yet.

Claims expire after the configured request deadline plus 30 seconds. A new
worker can reclaim expired jobs, and lease tokens reject late writes by a stale
worker. This provides at-least-once delivery attempts. A crash or ambiguous
network failure after Slack accepts a message can still cause a duplicate;
the stable Slack `client_msg_id` does not establish an exactly-once guarantee.
Unexpected worker failures leave the lease for recovery and count toward the
attempt limit. SIGTERM stops claims and allows current deliveries to drain.

One deployment namespace represents one Slack workspace/bot configuration.
Do not run workers with different credentials or channel mappings in the same
namespace. Development and production Compose use separate namespaces. If both
use the same Slack workspace, their rate gates are independent and Slack may
still throttle their combined traffic. Other apps posting to the same channel
can also cause throttling. Changing/removing an alias fails already-queued work
for its old channel with `notification_destination_changed`.

## Run and verify

From `backend/`, with the environment loaded:

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
# Separate terminal, same environment:
uv run python -m app.notifications.worker
```

The root development and production Compose stacks include
`notification-worker`, dependent on backend readiness/migrations. They default
to idle while disabled. After supplying credentials, from `nexgent/`:

```bash
docker compose up -d --build backend notification-worker
# Production:
docker compose -f compose.prod.yaml up -d --build backend notification-worker
# Optional extra development replicas:
docker compose up -d --scale notification-worker=2 notification-worker
docker compose logs --tail=100 notification-worker
```

Monitor worker logs and job status; `/health` is backend liveness and does not
prove a worker is consuming jobs. Pending work remains durable while the worker
is offline, but no alert or bounded queue admission policy is included.

Validation: the complete backend suite passed against an isolated PostgreSQL
18 instance (213 passed, no skips). The notification tests also passed on
SQLite (38 passed; two PostgreSQL row-lock tests skipped). Both Compose
configurations passed `docker compose ... config --quiet`; `git diff --check`
passed. Notification API schemas generated successfully; existing integration
proxy routes emit duplicate-operation-ID warnings. Tests cover browser and
service authentication, ownership, validation, idempotency races, concurrent
worker claims, channel/workspace rate gates, lease recovery, delivery/retry
outcomes, UTC responses, sanitized errors, and migration/model consistency.
The existing Python 3.14/FastAPI deprecation warnings remain. Tests used a
temporary local database and mocked Slack responses; no configured application
database or Slack workspace was used.

```bash
uv run pytest -q
# Use an isolated test PostgreSQL role with CREATE DATABASE privileges:
NEXGENT_TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/postgres \
  uv run pytest tests/test_notifications.py \
  tests/identity/test_accounts.py::test_final_schema_matches_models -q
```

### Live delivery verification — 2026-09-29

After the development credentials were configured, the backend's Slack sender
successfully posted one message titled "Nexgent test notification" to the
`default` destination. Slack returned message timestamp `1790665943.096889`.
This verified the bot credentials, message rendering, and channel access.

The running local API returned `401` for the configured notification service
token, so the test used the Slack sender directly. No application database
migration or container rollout was performed. Reload the backend and worker
with the updated environment, then run the submission/poll commands above and
verify `status: "sent"` and a `slack_ts`. API-to-worker delivery remains the
outstanding live end-to-end check. Credential values are not recorded here.

### Native block support — 2026-09-29

The API now accepts a validated native `blocks` layout and an optional generated
table/footer layout. This supersedes the earlier statement that callers cannot
supply Block Kit payloads. Supported block types, size limits, mention handling,
legacy idempotency compatibility and rollout are documented in
[Slack native blocks](slack-notification-native-blocks.md).
