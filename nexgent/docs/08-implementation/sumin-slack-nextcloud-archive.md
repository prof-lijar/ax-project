# Sumin Slack-to-Nextcloud Archive

Date: 2026-09-15

## Implementation

Sumin receives signed Slack events for configured channels, queues work in
PostgreSQL, archives files and upload context in Nextcloud, and answers mentions
with channel-scoped file links. A separate API and worker provide durable retries
and lease recovery. Configuration uses `SUMIN_*` variables in `agents/.env`;
the standalone Compose stack uses an external PostgreSQL database.

See the [workflow runbook](../../agents/workflows/sumin/README.md) for configuration,
permissions, recovery commands, and architecture details.

## Operation

Run from `agents/` after supplying the required environment values:

```bash
uv run --env-file .env python -m apps.sumin.manage migrate
docker compose --env-file .env -f compose.sumin.yaml up -d --build
uv run --env-file .env python -m apps.sumin.manage status
```

## Validation

The following command passed 45 tests and skipped one PostgreSQL test:

```bash
cd agents
.venv/bin/python -m pytest tests/unit/test_sumin.py tests/unit/test_slack_integration.py tests/contract/test_dependency_boundaries.py tests/integration/test_sumin_store.py
```

`git diff --cached --check` passed. The test run emitted Python 3.14 asyncio
deprecation warnings and an unawaited `ByteStream` cleanup warning.

## Remaining verification and limits

The PostgreSQL test requires a disposable database whose name contains `test`.
It was skipped because `SUMIN_TEST_DATABASE_DSN` was unset. Run from `agents/`:

```bash
SUMIN_TEST_DATABASE_DSN='postgresql://USER:PASSWORD@HOST/sumin_test' uv run pytest tests/integration/test_sumin_store.py
```

Live Slack/Nextcloud delivery and container execution were not verified in this
commit check; they require configured services and credentials. After starting
the stack above, upload a file to an approved channel and mention Sumin with its
filename; verify the archive, context, and returned link. Slack replies can repeat
after a worker crash. Nextcloud permissions remain operator-managed; historical
backfill, deletion synchronization, and content indexing are not implemented.
