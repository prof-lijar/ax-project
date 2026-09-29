# Slack notification native blocks

Date: 2026-09-29

The backend notification API now accepts validated Slack native blocks, as
requested for complete, readable weekly-report comparisons. Existing text and
field notifications keep their existing shape and idempotency fingerprints.
No database migration is required; the durable queue already stores JSON.

## API

`POST /api/notifications/slack` accepts an optional `blocks` array (at most 50).
Supported types are `header`, `section`, `context`, `divider`, and `table`.
Sections and contexts accept `plain_text` or `mrkdwn`; headers require plain
text. Markdown emphasis/lists are supported. Mentions and angle-bracket link
syntax remain literal: the renderer escapes `&`, `<`, `>` and sets `verbatim`.
Automatic parsing/unfurls remain disabled. Interactive accessories, image/file
blocks and rich-text table cells are not part of this contract.

One table per notification is supported, with 1–20 columns and at most 100 rows
including the header. Cells use `raw_text`; rows must be rectangular. All table
cells together are limited to 10,000 characters. Column settings support
left/center/right alignment and wrapping. The total escaped text budget is
30,000 characters so the accessible text fallback retains the full content.
Optional block IDs must be unique within the message.

Top-level `text` remains required as the notification summary. The renderer
includes the summary and all block content in the screen-reader fallback.
Native `blocks` own the layout and cannot be mixed with the generated-layout
`title`, `fields`, `table`, `footer`, or `url` options; mixed requests are rejected
rather than silently dropping information. Destination, severity, thread and
idempotency rules are unchanged.

```json
{
  "destination": "default",
  "text": "지난주 리포트 저장 현황",
  "severity": "warning",
  "blocks": [
    {"type": "header", "text": {"type": "plain_text", "text": "주간 리포트 저장 현황"}},
    {"type": "section", "text": {"type": "mrkdwn", "text": "*누락 1명* · 전주보다 1명 감소"}},
    {"type": "divider"},
    {"type": "table", "column_settings": [{"align": "left"}, {"align": "right"}],
     "rows": [
       [{"type": "raw_text", "text": "지역"}, {"type": "raw_text", "text": "누락(명)"}],
       [{"type": "raw_text", "text": "광명"}, {"type": "raw_text", "text": "1"}]
     ]},
    {"type": "context", "elements": [{"type": "plain_text", "text": "현재 가입자 기준"}]}
  ]
}
```

The generated-layout API also accepts an optional `table` object with `columns`,
`rows` and `align`, an optional `footer` (up to 3,000 characters), and optional
`locale: "ko"` for Korean severity labels. This is a convenience alternative to
supplying native blocks. New fields that are absent/empty are omitted from
canonical queue payloads, preserving legacy request fingerprints. Native
block validation occurs at submission; stored blocks survive retries unchanged.

## Weekly reporter

The producer sends seven native blocks: header, summary, date context, divider,
one table, divider and full calculation notes. Ten data rows pair last week
and two weeks ago for overall, Uljin, Yeongdeok, Gwangmyeong and Other. All
subscriber counts, successes, failures/missing counts, missing rates and
percentage-point differences are retained. Notes explain current-roster/address
selection, missing-report definitions, zero denominators, historical membership
limitations, existing reports, percentage points and rounding. No information
is dropped to shorten the message. Persisted pending notifications retain their
original payload, including the older layout, for safe idempotent replay.

## Deployment and verification

Rebuild the backend, notification worker and scheduler together so the new
producer contract is accepted by the API and rendered by the worker:

```bash
# From nexgent/:
docker compose -f compose.prod.yaml up -d --build backend notification-worker weekly-report-scheduler
# Verification from backend/:
.venv/bin/python -m pytest tests/test_notifications.py tests/test_notification_tables.py tests/test_notification_blocks.py -q
```

Backend tests cover native submission, queue replay, changed-body conflicts,
legacy fingerprints, complete rendering/fallback, schema limits, mention
handling and mocked Slack delivery. Agent tests validate the actual backend
schema/renderer and every regional value and note. Production database reports
are unchanged. Deployment and the API-to-worker live check are still pending;
prior running APIs returned 401 for their configured service tokens. The
previous live messages exercised the direct sender with earlier formats, not
the newly added native blocks. A later user-approved native-block test was delivered successfully through the
updated backend sender to `#nexgent-test` (Slack timestamp
`1790670192.238509`), with all aggregate data retained.

References: [Slack table blocks](https://docs.slack.dev/reference/block-kit/blocks/table-block/),
[section blocks](https://docs.slack.dev/reference/block-kit/blocks/section-block/),
[Block Kit reference](https://docs.slack.dev/reference/block-kit/blocks/).

Validation on 2026-09-29: full backend suite **243 passed, 5 skipped**; full
agent suite **713 passed, 25 skipped**. Changed agent files pass Ruff. Schema
export exposes the five native block variants. LangGraph validation (four graphs),
both Compose renders, local skill validation and `git diff --check` passed.
Tests used mocked Slack and temporary databases; opt-in live integrations remain
skipped. No deployment was performed. The subsequent direct-sender native-block test
passed; API-to-worker authentication remains a separate rollout check.
