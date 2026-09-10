# Scout Slack report delivery

Date: 2026-09-07 (Asia/Seoul)

## Implementation and architecture

The single ADK Scout Agent continues researching through `web_search` and
`web_fetch_and_extract`. `ScoutRunService` validates headings and fetched-source
URLs, atomically saves `report.md`, and writes `run_succeeded`. After closing
the per-run tools, it invokes `SlackNotifier` with the successful response.
This covers manual and scheduled requests to `POST /v1/scout/runs`. Raw ADK
discovery runs do not use this application service and do not notify Slack.

The notifier uses existing HTTPX to make one `chat.postMessage` call with the
run ID, source count, and complete report. The channel and token come only from
host configuration, never model output or request parameters. No agent tools,
models, response schemas, scheduler, or frontend code were changed.

Delivery is awaited with a 12-second overall timeout (10-second HTTP timeout).
Research timestamps and duration end before delivery, so HTTP response latency
may exceed the reported research duration by the delivery time. Slack failure
does not change a successful research response or append `run_failed`.

## Configuration

Add to `ansimk_scout_agent/.env`:

```dotenv
SCOUT_SLACK_BOT_TOKEN=xoxb-your-bot-oauth-token
SCOUT_SLACK_CHANNEL_ID=C0123456789
```

Use the Bot User OAuth Token from the installed app. Ensure the app has the
`chat:write` bot scope, reinstall it if scopes changed, and invite it to the
target channel. Use the channel ID, not its display name. See the official
[chat.postMessage reference](https://docs.slack.dev/reference/methods/chat.postMessage/).

The existing dotenv loader reads the project `.env` with `override=False`:
process environment values take precedence. For the systemd deployment,
add these variables to the existing protected EnvironmentFile described in
`scout-systemd-supervision.md` and restart with:

```bash
sudo systemctl restart nexgent-scout.service
```

No real credentials were created or edited, and no running service was restarted
as part of this implementation. Both variables absent/blank disables delivery;
one missing records `incomplete_configuration` without network access. Readiness
continues to describe model configuration and does not probe Slack.

## Audit and limitations

`execution.jsonl` receives `slack_delivery_sent`, `slack_delivery_failed`, or
`slack_delivery_skipped` after `run_succeeded`. Thus the last event is no longer
necessarily the research terminal event. Delivery events contain a fixed safe
reason code, not tokens, channel IDs, reports, or upstream error bodies. If the
delivery audit itself fails, a safe process warning records the run ID.

There is no retry, durable outbox, delivery-status API, or exactly-once guarantee.
A timeout may mean Slack accepted the message but the response was lost; process
termination after persistence may omit delivery. Rate limits record
`rate_limited` without retrying or repeating research.

Reports are converted from the Scout Markdown subset to Slack mrkdwn: headings
become bold labels, Markdown bold becomes Slack bold, list markers become
bullets, and Markdown HTTP(S) links and bare URLs become explicit clickable
Slack links. Inline and fenced code are preserved. Slack control characters are
escaped before links are generated, and automatic mention parsing and link
previews remain disabled. Messages over
39,000 escaped characters are rejected with `message_too_long` rather than
silently truncated; the complete local report remains available.

Existing validation checks structure and source URL provenance, not semantic
support for every statement. Slack delivery does not add semantic verification.

## Validation and remaining live verification

Offline tests cover successful delivery after persistence, HTTP/API failures,
rate limiting, timeouts, malformed responses, absent/partial configuration,
mention escaping, safe logs, audit failures, and no delivery for invalid reports.
The complete existing unit and API contract suite passed: **61 tests**, with two
upstream ADK deprecation/experimental warnings. Validation commands from the
Scout project directory:

```bash
uv sync --all-groups
uv run --no-sync pytest
uv run --no-sync ruff check app tests
uv run --no-sync ruff format --check app tests
git diff --check
```

Lint, formatting, and whitespace checks passed. Test/check invocations used
`UV_CACHE_DIR=/tmp/scout-uv-cache` because the sandbox's default uv cache was
read-only; dependency synchronization used approved access to the existing cache.

No live model run or real Slack message was sent: this task assumes configuration
will be supplied in `.env`, and this checkout has only `.env.example`. After
setting the variables and restarting Scout, run this once to verify the full
research-to-channel path (it posts a real report):

```bash
curl -fsS -X POST http://127.0.0.1:8091/v1/scout/runs \
  -H 'Content-Type: application/json' \
  -d '{"topic":"고독사 예방 AI IoT 서비스 최근 동향"}'
```

Confirm the returned report appears in the configured channel and inspect the
returned `log_artifact` under `SCOUT_OUTPUT_ROOT` for `slack_delivery_sent`.

## Update: 2026-09-07 — Slack report formatting

The original payload disabled mrkdwn and sent literal Markdown, so headings,
bold markers, and source links were displayed as raw text. The notifier now
converts the report as described above and enables mrkdwn. Saved report.md and
the research API response remain unchanged. This is a bounded Scout formatter,
not a complete CommonMark renderer (tables/reference-link syntax are not handled).
See [Slack message formatting](https://docs.slack.dev/reference/methods/chat.postMessage/).

Regression checks cover headings, bold, bullets, Korean text, explicit and bare
links, URL underscores/parentheses, mention escaping, code preservation, and
the actual HTTP payload. All 65 tests passed; Ruff lint and whitespace checks
passed. Live visual verification was not performed and no
existing channel messages were edited. From Nexgent, rebuild the service:

```bash
sudo docker compose up -d --build --no-deps scout
```

Then run research once in the UI and confirm formatted output in Slack.
