# October 12 motion and remote-control count correction

Configuration update (2026-10-27): all agent configuration now comes from
`agents/.env`; see [unified environment](../../docs/unified-environment.md).
Production migration uses `LIVE_PROD_*` and development migration uses
`LIVE_DEV_*`. Older per-tool env files are no longer read.

Date: 2026-10-26 (Asia/Seoul)

Copies each ward's **October 19–25, 2026 previous-week counts** into that
ward's **October 12–18, 2026 current-week counts** in production
`ansimk.resources_ward_weekly_report`:

| October 19 source | October 12 destination |
| --- | --- |
| `living_activity.activity_detection.metrics.previous_week` | `living_activity.activity_detection.metrics.current_week` |
| `living_activity.remote_control_usage.metrics.previous_week` | `living_activity.remote_control_usage.metrics.current_week` |

Also refreshes each destination's `current_week_display`, `comparison_percent`,
and `comparison_display` using the existing reporter policy and the October 12
report's unchanged `previous_week` denominator. Null counts retain unavailable
semantics; zero denominators produce an unavailable comparison.

Previous-week counts, classifications, descriptions, summaries, guardian actions,
scores and all other report fields are preserved. The preview records calculated
before/after classifications for review; existing text can disagree with the
corrected numbers. October 19 reports, local archive rows and exported artifacts
are not changed. No reports are created or deleted. Changed rows receive a new
`updated_at`.

From the `playground` directory, preview:

```bash
bash fix-oct12-counts/run.sh
```

Inspect the printed JSON artifact, then apply and verify:

```bash
bash fix-oct12-counts/run.sh --write
bash fix-oct12-counts/run.sh
```

After a successful write, `would_update` should be zero. Check `skipped`
separately: a missing October 19 report (`missing_source`) or malformed dates,
structure or counts (`invalid_report`) skips the entire ward, including both
signals. Missing fields are invalid, not zero. Only saved October 12 reports
are selected; missing October 12 rows are outside the selected set. Exit codes:
`0` complete, `2` skipped wards (eligible writes still commit), `1` failure.

The launcher uses `../.venv/bin/python` (override with `PYTHON_BIN`), `asyncpg`,
`python-dotenv`, OpenSSH and `sshpass`. Connection settings come from
`agents/.env`; exported variables take precedence.
It opens and closes its own production SSH tunnel using `LIVE_PROD_SSH_*` and
`LIVE_PROD_DB_HOST`. Python connects to the local loopback listener; an occupied
`LIVE_PROD_TUNNEL_PORT` aborts the command.
`bash fix-oct12-counts/run.sh --help` does not open a connection.

Every run saves original rows for both weeks and the plan in an ignored
`backups/` directory (override with `--output-dir PATH`). These contain private
report data. Files use mode `0600`, newly created directories `0700`, and existing
artifacts are never overwritten. Write mode flushes the backup to disk before
updating, locks both weeks, and applies all eligible updates in one
repeatable-read transaction with original-JSON conflict checks. Any update
failure rolls back the transaction. A fresh plan is built on every run.

Run while generation, migration and delivery for these weeks are idle. Ordinary
regeneration or migration can overwrite this correction. Only `mode: committed`
confirms successful commit; a `pre_write_backup` artifact alone does not. After
an uncertain commit, preview again before retrying. Reruns are idempotent.
Recovery uses the original October 12 `report_data` from that run's backup in a
separate ward/week-scoped update; avoid overwriting subsequently regenerated rows.

Offline verification:

```bash
../.venv/bin/python -m unittest discover -s fix-oct12-counts -p 'test_*.py'
```

Validation on 2026-10-26: the combined scheduler, notification, deployment,
and correction-tool regression run passed all 140 tests. Changed Python files
passed Ruff, and the launcher passed `bash -n`. Correction tests use synthetic
rows and a fake connection; live database correction was not run as part of
this pre-commit validation.
