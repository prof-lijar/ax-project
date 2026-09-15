# Sumin Shared Agent Schema

Date: 2026-09-15

## Implementation

Sumin now uses `agent.sumin_events`, `agent.sumin_channels`,
`agent.sumin_files`, `agent.sumin_contexts`, and `agent.sumin_migrations`
through the existing `AGENT_DATABASE_DSN`. Runtime, readiness, and management
queries use the new table names.

The migration moves legacy tables in place under a transaction advisory lock,
prefixes legacy index names, and rejects source/destination conflicts. Existing
rows, grants, constraints, and migration history are retained. The legacy schema
is left intact. Migration requires table ownership and CREATE on `agent`;
runtime roles require USAGE on `agent` and table privileges.

## Operations

Stop old consumers before applying the migration. From `nexgent/`:

```bash
sudo docker compose stop sumin-events sumin-worker
sudo docker compose up --build -d
```

The migration service runs before consumers. No DSN change is required.
See [Sumin operations](../../agents/workflows/sumin/README.md) for details.

## Validation and remaining verification

From `nexgent/agents/`:

```bash
.venv/bin/pytest tests/unit/test_sumin.py tests/unit/test_slack_integration.py tests/contract/test_dependency_boundaries.py tests/integration/test_sumin_store.py
```

Result: 72 passed, 5 skipped. Database tests skipped because
`SUMIN_TEST_DATABASE_DSN` was not configured. The run emitted Python/pytest
deprecation warnings and an unawaited ByteStream cleanup warning.
`git diff --check` passed.

Live PostgreSQL migration and end-to-end deployment were not run during this
commit preparation. Run the database regression suite against a disposable
database whose name contains `test`:

```bash
SUMIN_TEST_DATABASE_DSN='postgresql://USER:PASSWORD@HOST/sumin_test' .venv/bin/pytest tests/integration/test_sumin_store.py
```

After the rollout commands above, check services with
`sudo docker compose ps` and queue access with
`sudo docker compose exec sumin-worker uv run --no-sync python -m apps.sumin.manage status`.
Upload a new Slack file and verify its Nextcloud archive to complete the live
end-to-end check.
