# Sumin Single-Workspace Channel Folders

Date: 2026-09-15

## Implementation

Sumin now archives files at `<root>/<channel-name>/<file-id>--<filename>`.
Workspace IDs remain in authorization checks and database keys. The one-time
`channel-folders-v2` SQL migration removes the legacy workspace segment from
stored channel and file paths, preserving custom roots and stable channel names.
Migration locking prevents concurrent application; path collisions abort the
transaction. Nextcloud objects and completed event states are unchanged.

## Operations and limitations

This layout assumes one Slack workspace. The rollout assumes the operator clears
the old Nextcloud archive while consumers are stopped; the migration does not
move files or backfill completed events. From `nexgent/`:

```bash
sudo docker compose stop sumin-events sumin-worker
# After the operator clears the old Nextcloud archive:
sudo docker compose up --build -d
```

Upload a new Slack file and verify its channel folder in Nextcloud after startup.
See [workflow operations](../../agents/workflows/sumin/README.md) for configuration.

## Validation

Executed from `agents/`:

```bash
.venv/bin/python -m pytest tests/unit/test_sumin.py tests/integration/test_sumin_store.py
```

Result: 57 passed, 3 skipped. PostgreSQL integration tests were skipped because
`SUMIN_TEST_DATABASE_DSN` was not configured. The run emitted Python/asyncio
deprecation warnings and an unawaited async cleanup warning. Staged whitespace
validation (`git diff --cached --check`) passed.

Remaining database verification, using a disposable database with `test` in its
name, from `agents/`:

```bash
SUMIN_TEST_DATABASE_DSN='postgresql://USER:PASSWORD@HOST/sumin_test' .venv/bin/python -m pytest tests/integration/test_sumin_store.py
```

Live Slack-to-Nextcloud verification was not run during the commit task because
it requires deployment and a new Slack upload. Run the rollout commands above,
upload a new file, and confirm `<root>/<channel-name>/<file-id>--<filename>`.
