# Monthly Risk Day and Same-Day Recovery Migration

Date: 2026-10-22

## Implemented behavior

The operator tools under `agents/playground/migrate/` recalculate archived
monthly risk summaries and copy the resulting records to live dev. These tools
run independently of agent graphs, report generation, scheduling, and delivery.

Local calculation reads `archive.resources_ward` and
`archive.analysis_wardevaluation` and upserts
`archive.resources_ward_monthly_risk_count` by `(ward_id, month)`. In
`Asia/Seoul` by default, each calendar day containing DANGER counts once.
`risk_days` stores sorted, distinct day-of-month numbers and
`total_risk_count` equals its length. Days with a later STABLE evaluation on
the same local date count once in `danger_stable_days` and
`total_danger_stable_count`. Intermediate states are allowed; equal timestamps
and recovery after midnight do not qualify. A subsequent DANGER does not undo
an already observed same-day recovery. Both arrays are empty for no matching
days. Removed weekly columns are not referenced.

No month arguments means the complete source evaluation month range; explicit
inclusive start/end months are also supported. Each local month uses a source
snapshot and independent transaction. Apply serializes destination writes,
updates differing counts/arrays, and reports success only after commit.
Rerunning replaces values rather than incrementing them. Logs include stage
names, monthly progress, counts, elapsed time, and 15-second heartbeats.

The dev copy reads all stored local monthly rows from a consistent snapshot,
opens an owned SSH tunnel, stages rows in batches, validates data, and upserts
`ansimk.resources_ward_monthly_risk_count` in one destination transaction.
Rows whose ward ID is absent from dev `ansimk.resources_ward` are excluded for
all months. Logs and receipts report skipped wards and rows separately from
eligible, inserted, updated, and unchanged rows. Invalid source data still
aborts the copy. Every eligible copied key is verified before commit.
Destination IDs are allocated/preserved; the other eight columns, including
source timestamps, are copied. Extra destination keys are retained.

The target tables and their nine-column schema must already exist. The tools
do not create schema, synchronize ward records, or delete business rows.
Source history must be complete before recalculation. Cross-midnight recovery
is deliberately excluded, and the recovery fields describe whether recovery
occurred at least once rather than the final daily state.

## Configuration and operation

Use the existing `agents/.venv`, `asyncpg`, `python-dotenv`, `ssh`, and `sshpass`.
No separate dependency installation is introduced. `playground/.env` is loaded
relative to the script; exported variables take precedence. Local selection
uses `SOURCE_DATABASE_DSN`, then the existing storage/Ansimk DSN configuration.

Dev settings are isolated under `LIVE_DEV_DB_*` and `LIVE_DEV_SSH_*`. The required
keys are DB HOST/USER/PASSWORD and SSH HOST/ID/PASSWORD. Optional DB PORT/NAME/
SCHEMA/SSL and SSH PORT are documented in the tool README. The configured dev
endpoint can include an `http://` prefix, which is normalized to a hostname.
DB TLS defaults to `prefer` for the verified server's lack of PostgreSQL TLS;
an explicit SSL setting is honored. SSH passwords use a pipe rather than
command arguments, and the owned tunnel is cleaned up on failure or completion.

From `agents/playground/migrate`:

```bash
# Preview local calculation, or commit it.
bash run.sh
bash run.sh --apply

# Optional inclusive local range.
bash run.sh --start-month 2026-10 --end-month 2026-10 --apply

# Preview dev copy, or commit eligible rows.
bash run.sh -target dev
bash run.sh --migrate-to-live -target dev
```

Only `dev` is supported by the live-copy CLI. Without `--migrate-to-live`,
staging is rolled back and no persistent target change is made. A failed copy
rolls back its whole destination transaction; rerunning reconciles an uncertain
commit. Local calculation recovery reruns the same month range, preserving
months already committed.

## Validation and remaining live work

All 35 tests passed with PostgreSQL fixtures enabled. SQL tests use synthetic
rows and temporary tables; no business table is written by the suite. Cases
cover temporal ordering, repeated transitions, timezone/month boundaries,
array normalization, zero/stale values, idempotence, commit receipts, copy
rollback, timestamps and IDs, invalid data, missing parents, and all parents
missing. Ruff, CLI help, and shell syntax checks passed.

From `agents/playground/migrate`:

```bash
../../.venv/bin/ruff check --target-version py310 .
RUN_MIGRATION_SQL_TESTS=1 ../../.venv/bin/python -m unittest discover -s . -p 'test_*.py'
bash -n run.sh
```

On 2026-10-22 the completed local data was checked read-only: 113,781 rows,
6,693 wards, no array/count/subset consistency errors, and all ten sampled rows
matched independent source recomputation. Source-to-destination dev preview
successfully staged 113,781 rows, skipped 663 rows belonging to 39 absent dev
wards, and planned 113,118 inserts. The staging transaction was rolled back;
the live dev copy has not been committed by this work. Its remaining execution
command is `bash run.sh --migrate-to-live -target dev`; capture the committed
receipt and repeat the preview to confirm eligible rows are unchanged.

See [operator configuration, contracts and commands](../../agents/playground/migrate/README.md).
