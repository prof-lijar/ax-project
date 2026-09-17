# Sumin Model-Directed File Search

Date: 2026-09-17

Sumin mention searches now use the shared OpenAI-compatible model adapter to
browse channel-scoped archive metadata, inspect candidates, verify live Nextcloud
availability, and select up to ten files for attachment in the requesting Slack
thread. The archive path remains deterministic. Source links accompany attachments.

The workflow limits discovery to eight structured actions with a 20-second
deadline per model call. Tools own SQL, channel scope, and URLs; delivery accepts
only inspected and verified file IDs. File contents and credentials are excluded
from model input. Nullable filename, upload-time, and uploader columns preserve
metadata without inventing historical upload times. Legacy timestamps are labeled
as first receipt. Downloads enforce the configured per-file size limit.

## Operations

Apply the updated Slack manifest and reinstall the app to grant `files:write`.
Configure the shared model endpoint as described in the
[Sumin runbook](../../agents/workflows/sumin/README.md). From `nexgent/`, rebuild
and start services with `sudo docker compose up --build -d`; the migration service
applies the additive metadata columns before workers start. For native execution,
run `uv run --env-file .env python -m apps.sumin.manage migrate` from `agents/`.

## Validation

From `agents/`, ran:

```sh
.venv/bin/pytest tests/unit/test_sumin_search.py tests/unit/test_sumin.py tests/unit/test_slack_integration.py tests/contract/test_dependency_boundaries.py tests/integration/test_sumin_store.py tests/evals/test_sumin_search_model.py
.venv/bin/ruff check workflows/sumin/search.py workflows/sumin/service.py workflows/sumin/store.py packages/integrations/src/ax_integrations/nextcloud.py packages/integrations/src/ax_integrations/slack_files.py tests/unit/test_sumin.py tests/unit/test_sumin_search.py tests/integration/test_sumin_store.py tests/evals/test_sumin_search_model.py
```

Result: 89 passed, seven skipped; Ruff passed. Pytest emitted asyncio deprecation
warnings and an unawaited ByteStream cleanup warning. `git diff --check` passed.

The five database cases require an explicitly configured disposable database;
the two live-model cases require opt-in and model configuration. Remaining commands
from `agents/` are:

```sh
SUMIN_TEST_DATABASE_DSN='<disposable-test-database-dsn>' uv run pytest tests/integration/test_sumin_store.py
SUMIN_RUN_MODEL_EVAL=1 uv run --env-file .env pytest tests/evals/test_sumin_search_model.py
```

No deployment or live Slack/Nextcloud end-to-end check was performed during this
commit preparation. After deployment, inspect services with
`sudo docker compose ps -a sumin-migrate sumin-events sumin-worker` and
`sudo docker compose logs --tail=100 sumin-migrate sumin-events sumin-worker`,
then upload a test file and request it in the same Slack channel to verify attachment
delivery. Partial delivery can repeat on retry. Search has no file-content indexing,
conversation memory, or deletion synchronization; finite pagination may leave
unseen results.
