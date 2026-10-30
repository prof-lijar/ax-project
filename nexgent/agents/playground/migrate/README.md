# Monthly danger-day and recovery-day migration

Configuration update (2026-10-27): all agent configuration now comes from
`agents/.env`; see [unified environment](../../docs/unified-environment.md).
Production migration uses `LIVE_PROD_*` and development migration uses
`LIVE_DEV_*`. Older per-tool env files are no longer read.

From `playground/migrate`, preview or apply the full evaluation history:

```bash
bash run.sh
bash run.sh --apply
```

With neither month option supplied, the script uses the earliest and latest
`evaluated_at` months in `archive.analysis_wardevaluation`, using `Asia/Seoul`
(override with `--timezone`). Range detection includes all risk levels. Every
intervening month is processed, including months with no evaluations. An empty
source table exits without changes. The range is printed and fixed for that run.

For a selected range, provide both inclusive endpoints:

```bash
bash run.sh --start-month 2026-10 --end-month 2026-10
bash run.sh --start-month 2026-10 --end-month 2026-10 --apply
```

`YYYY.MM` is also accepted. Providing only one month option is an error.

The launcher uses the existing `agents/.venv/bin/python`; `PYTHON_BIN` can
override it. Connection settings match the other playground migrations:

1. Load `agents/.env`, preserving exported variables.
2. Use a nonblank `SOURCE_DATABASE_DSN` if configured.
3. Otherwise read `WEEKLY_REPORT_STORAGE_DATABASE_DSN`, then `ANSIMK_DATABASE_DSN`,
   from the environment or `agents/.env`, with environment values taking
   precedence for each key.

Paths resolve relative to the script. All three tables are in `archive` on the
same database; production target credentials and SSH settings are not needed.

The source tables are `archive.resources_ward` and
`archive.analysis_wardevaluation`. The destination is
`archive.resources_ward_monthly_risk_count`. Every source ward receives one row
per selected month. The script recalculates these four destination columns:

| Column | Meaning |
| --- | --- |
| `total_risk_count` | Number of local calendar days containing at least one DANGER evaluation |
| `risk_days` | Sorted, distinct day-of-month numbers with DANGER evaluations |
| `total_danger_stable_count` | Number of local days with DANGER followed strictly later by STABLE on that same day |
| `danger_stable_days` | Sorted, distinct day-of-month numbers satisfying the recovery rule |

Multiple danger evaluations or recoveries on the same day count once. A stable
evaluation before all danger evaluations does not count as recovery. Equal
timestamps do not establish a recovery. Intermediate evaluations are allowed:
`DANGER → CAUTION → STABLE` qualifies. A later DANGER on the same day does not
remove an earlier qualifying recovery; these fields record whether recovery
occurred at least once, rather than the day's final status.

Days and months use the selected timezone. For example, DANGER at 23:59 followed
by STABLE at 00:01 the next day does not qualify, even though only two minutes
elapsed. Different wards cannot contribute to one another's recovery counts.
The query groups danger dates first, then checks for a later STABLE evaluation
before that local day's next midnight using the source ward/timestamp index.

Example: DANGER on October 3, 14 and 20, with same-day recovery on October 14
and 20, yields:

```text
total_risk_count          = 3
risk_days                 = {3,14,20}
total_danger_stable_count = 2
danger_stable_days        = {14,20}
```

Each count equals its array's length. `danger_stable_days` is a subset of
`risk_days`, and both counts are at most the month's number of days. No matching
days gives count 0 and an empty integer array (`{}`). Existing NULL arrays,
stale values, and recovery-only differences are updated. No weekly columns are
referenced. The four columns must already exist; no schema changes are made.

Upserts use `(ward_id, month)` with months formatted as `YYYY.MM`. All four fields
are replaced rather than incremented. Inserts use identity and timestamp
defaults. Updates preserve `id` and `created_at`, change `updated_at`, and skip
rows whose four fields already match. Repeating a run is idempotent. Rows outside
the selected months are untouched. Missing source history produces zero or
incomplete results, so select months whose archive data is ready.

Each month commits independently using a consistent source snapshot. Apply
holds a target table lock for that month, blocking competing target writes while
allowing ordinary reads. Source evaluations arriving after the snapshot require
a rerun. A lock wait beyond 10 seconds or a SQL statement beyond 30 minutes aborts
the current month. Earlier committed months remain committed. Rerun the same
range to recover, including after a connection loss with an uncertain commit.

Progress logs show timestamps, connection and range detection, month position,
lock waiting, calculation, inserts/updates/unchanged rows, and commit stages.
A heartbeat prints every 15 seconds during long operations. Per-month JSON
receipts include `danger_days` and `danger_stable_days` summed across wards,
month progress, percentage, and elapsed seconds. The receipt's
`danger_stable_days` is a summary count; the table column of the same name is an
integer array. Apply receipts appear only after successful commit.

To also save progress:

```bash
set -o pipefail
bash run.sh --apply 2>&1 | tee migration-progress.log
```

Omit `--apply` for a preview; use `tee -a` to append. `pipefail` preserves migration
failures in the pipeline's exit status. Database permissions must allow SELECT
on the source and target, INSERT/UPDATE on the target, and identity allocation.

Run offline checks from `playground/migrate`:

```bash
../../.venv/bin/python -m unittest discover -s . -p 'test_*.py'
```

Enable PostgreSQL fixture tests using the configured connection:

```bash
RUN_MIGRATION_SQL_TESTS=1 ../../.venv/bin/python -m unittest discover -s . -p 'test_*.py'
```

These tests use synthetic rows. Aggregation and preview tests run read-only;
the upsert test writes only a temporary table and rolls its transaction back.
No business table data is changed. Tests cover same-day ordering, repeated
recoveries, intermediate states, equal timestamps, timezone and month boundaries,
empty arrays, stale values, and idempotent inserts/updates.

Editing the script does not update stored counts. Run with `--apply` to populate
the new recovery fields, then regenerate the PDF if an updated report is needed.

## Copy the local risk table to live dev

`migrate-to-live.py` copies every stored row from
`archive.resources_ward_monthly_risk_count` on the local database into
`ansimk.resources_ward_monthly_risk_count` on the live dev database. It copies the
stored monthly counts and arrays directly; it does not recalculate evaluations
or copy any other business tables.

From `playground/migrate`, preview first, then commit with the requested flag:

```bash
bash run.sh -target dev
bash run.sh --migrate-to-live -target dev
```

The launcher selects `migrate-to-live.py` when it sees `--migrate-to-live`,
`-target`, or `--target`. Existing `bash run.sh --apply` continues to recalculate
local risk/recovery data. The copy script can also be run directly with the
existing virtual environment:

```bash
../../.venv/bin/python migrate-to-live.py --migrate-to-live -target dev
```

The script loads `agents/.env`, preserving exported environment variables,
and resolves the local source DSN using the same rules described above. Dev
connection settings use `LIVE_DEV_*`, independently of production
`LIVE_PROD_*` settings:

| Variable | Purpose / default |
| --- | --- |
| `LIVE_DEV_DB_HOST` | Required remote PostgreSQL hostname/IP, reached from the SSH server; bare endpoints and `http(s)://` endpoint URLs are accepted |
| `LIVE_DEV_DB_USER` | Required dev database user |
| `LIVE_DEV_DB_PASSWORD` | Required dev database password |
| `LIVE_DEV_DB_PORT` | Remote PostgreSQL port; default 5432, or the endpoint URL's explicit port |
| `LIVE_DEV_DB_NAME` | Database name; default `ansimk` |
| `LIVE_DEV_DB_SCHEMA` | Destination schema; default `ansimk` |
| `LIVE_DEV_DB_SSL` | PostgreSQL TLS mode; default `prefer`, compatible with the configured dev server's lack of PostgreSQL TLS support |
| `LIVE_DEV_SSH_HOST` | Required SSH server hostname/IP |
| `LIVE_DEV_SSH_ID` | Required SSH login user |
| `LIVE_DEV_SSH_PASSWORD` | Required SSH login password |
| `LIVE_DEV_SSH_PORT` | SSH port; default 22 |

Existing `ssh` and `sshpass` are used. SSH password input travels through a pipe,
not command arguments. The script opens its own tunnel on an available loopback
port and closes its process group on completion or failure. The remote DB host
is forwarded as configured; no production endpoint is hardcoded. Explicit TLS
settings are honored. SSH uses the existing scripts' `accept-new` host-key
policy, rejecting changed keys.

All source rows are streamed from one read-only snapshot into a temporary dev
staging table in batches of 5,000. Preview stages and validates the full copy,
then rolls back its transaction; it makes no persistent target changes. Apply
locks the destination table against competing writes, validates, upserts, and
verifies all eligible copied keys before one atomic destination commit. Ordinary reads
remain permitted. Progress and heartbeat logs show each stage and batch.

Validation checks nonnull arrays, sorted/distinct day numbers, valid monthly
day ranges, matching array lengths and counts, and recovery days being a subset
of danger days. Rows whose ward ID is missing from the dev `resources_ward`
table are skipped for every month. Logs list missing IDs (up to 50) and report
skipped ward and row counts. JSON receipts distinguish `source_rows`,
`eligible_rows`, `skipped_wards`, and `skipped_rows`; insert, update, and unchanged
counts refer only to eligible rows. Preview and apply use the same filter.
Invalid source data still aborts the copy. The destination's table and nine-column
schema must already exist, including the `(ward_id, month)` unique key. The database role needs TEMP
permission, source/target SELECT, target INSERT/UPDATE, and identity allocation.

Destination IDs are generated for new rows and preserved on updates. All other
columns are copied from the local snapshot, including `created_at` and
`updated_at`. Conflicts on `(ward_id, month)` replace differing source-owned
values; identical rows are skipped. Destination rows with no matching local key
are preserved. No destination DELETE, TRUNCATE, schema creation, or ward
synchronization is performed. Skipped rows are removed only from the temporary
staging table. Repeating the command is idempotent and reconciles an uncertain commit.

The PostgreSQL fixture test suite also covers preview rollback, exact array and
timestamp copying, idempotence, destination ID preservation, skipping all months
of missing dev parents (including when all parents are missing), and invalid
source arrays. It uses temporary tables on the configured local
connection; no business table is written during tests.

The production daily-risk scheduler now reuses the workflow-owned copy
implementation for only the reconciled month, after the local daily commit.
The manual command above retains its full-history scope and preview default.
