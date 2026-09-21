# Weekly reporter database migration

This tool copies saved weekly reports from the local database to the live
production database. Both databases use `ansimk.resources_ward_weekly_report`.
It transfers existing report data; it does not generate reports or call an LLM.

The Monday scheduler also invokes this script automatically with `--write`
and `--week-start` set to the report week's Monday after the bulk job confirms
local storage. See [scheduler deployment and recovery](../../apps/weekly_report_scheduler/README.md)
for production configuration, saved receipts, and failure handling.

Rows match on `(ward_id, week_start_date)`:

| Production row | Result |
| --- | --- |
| Does not exist | Insert the source report |
| Exists with different report fields | Update it from the source |
| Already has identical report fields | Update it anyway and refresh `updated_at` |
| Ward is absent from production `resources_ward` | Skip its report and print the ward ID and report week |

## Files

| File | Purpose |
| --- | --- |
| `migrate.sh` | Entry point: opens SSH, runs the migration, then closes SSH |
| `migrate.py` | Reads source reports, previews changes, and applies transactional upserts |
| `.env.example` | Configuration template without passwords |
| `.env` | Your private connection settings; ignored by Git |

## Connection settings

The source and production database credentials are separate. The source reads
`agents/.env`, using `WEEKLY_REPORT_STORAGE_DATABASE_DSN` first and falling back
to `ANSIMK_DATABASE_DSN`. Leave `SOURCE_DATABASE_DSN` blank to use this behavior.
An explicit `SOURCE_DATABASE_DSN` overrides it. Exported environment variables
take precedence over dotenv values.

Configure production and SSH in `playground/weekly-reporter/.env`:

```dotenv
# Optional; blank uses the weekly reporter agent's source configuration.
SOURCE_DATABASE_DSN=

# SSH server login, separate from the PostgreSQL login.
SSH_HOST=211.188.52.211
SSH_ID=root
SSH_PASSWORD='your-ssh-password'

# PostgreSQL connection through the local SSH tunnel.
TARGET_DB_HOST=127.0.0.1
TARGET_DB_PORT=15432
TARGET_DB_NAME=ansimk
TARGET_DB_USER=your-production-db-user
TARGET_DB_PASSWORD='your-production-db-password'
TARGET_DB_SSL=require
```

`SSH_HOST` is the server that can reach the private production database.
`TARGET_DB_HOST=127.0.0.1` is correct: the script opens a local forwarding port
that carries the database connection through SSH. The remote forwarding
 destination is currently fixed in `migrate.sh` as
`pg-34le5q.vpc-cdb-kr.ntruss.com:5432`.

```text
Migration -> 127.0.0.1:15432 -> SSH server -> private production PostgreSQL:5432
```

SSH reads `SSH_PASSWORD` automatically through a file descriptor. The password
is not printed or placed in command-line arguments. No separate terminal or
interactive password entry is needed. New SSH host keys are accepted and saved;
changed keys are rejected. A verified key can be placed in `~/.ssh/known_hosts`
before the first run. Database TLS defaults to `require`; certificate identity
verification requires `verify-full`, a trusted PostgreSQL CA, and a connection
hostname that both resolves to the tunnel and matches the certificate.

The configured production endpoint rejected PostgreSQL TLS negotiation during
connection testing. With operator approval, the local migration `.env` now uses
`TARGET_DB_SSL=disable`; the template retains `require`. SSH still encrypts the
connection to the SSH server, while the SSH-server-to-database leg uses no
PostgreSQL TLS. The source DSN retains its separate required-TLS setting.

## Setup

From the `agents` workspace root:

```bash
cd playground/weekly-reporter
```

If `.env` does not exist yet, create it from the template. Keep an already
configured `.env`:

```bash
[ -f .env ] || cp .env.example .env
chmod 600 .env
```

Fill in the settings above. The scripts require the workspace `.venv` with
`asyncpg` and `python-dotenv`, OpenSSH, and `sshpass`. On Debian/Ubuntu, install
`sshpass` if missing:

```bash
sudo apt-get install sshpass
```

`sshpass` supplies the configured password to SSH without prompting.

## Test without changing production data

Preview all saved source reports:

```bash
./migrate.sh
```

The script opens SSH automatically, reads both databases, reports the planned
counts, and closes SSH. Example output (illustrative counts):

```json
{"mode": "preview", "source": 100, "insert": 60, "update": 38, "unchanged": 0, "skipped": 2}
```

`source` is the number of selected local reports. The remaining counts show
how many would be inserted or updated. Every matching row counts as an update,
even when its report content is identical. `unchanged` remains zero. `skipped`
counts reports whose ward is absent from production; each is printed with its
ward ID and report week in both preview and write mode. Such skips do not fail
the command, including when every selected report is skipped. Thus
`source = insert + update + skipped`. Preview does not issue
database writes and does not verify every production write permission or
constraint. Counts may change if either database changes before the write run.

## Run the migration

Apply all saved source reports:

```bash
./migrate.sh --write
```

Successful completion prints `"mode": "committed"` with the counts. There is
no additional confirmation prompt. Without `--week-start`, every source week
is selected.

To preview and then migrate only one week, use the same date for both commands:

```bash
./migrate.sh --week-start 2026-08-31
./migrate.sh --week-start 2026-08-31 --write
```

The date selects rows whose `week_start_date` equals that value.

## Verify afterward

Run the preview again with the same scope:

```bash
./migrate.sh
# Or, for a single-week migration:
./migrate.sh --week-start 2026-08-31
```

After a successful migration, `insert` should be zero and `update + skipped`
should equal `source` if neither database changed in between. This preview reports planned
upserts, not content differences. Each subsequent `--write` updates matching
reports again and refreshes `updated_at`, even for identical content. To verify
the copied content, compare the selected source and production report fields;
preview counts alone do not certify content equality.

Show available options without opening SSH:

```bash
./migrate.sh --help
```

## Transaction behavior and requirements

The source is read-only. Production generates its own row IDs. Inserts keep
source `created_at` (or use NOW); updates preserve production `created_at`.
All inserted and updated rows use NOW for `updated_at`. Nothing is deleted, and missing wards
are not created. Ward IDs must identify the same people in both databases.

All production writes share one transaction; errors before commit roll it back.
Write mode locks the report table against other writers until commit. Run during
an appropriate migration window and pause delivery work that could conflict
with the same reports. Connection loss during commit can leave the outcome
uncertain; run a preview to inspect the resulting state before retrying.

The production report table must already exist with its ward/week unique
constraint. The migration role needs SELECT/INSERT/UPDATE and identity-sequence
access, plus SELECT on `ansimk.resources_ward`. Reports for missing target wards
are skipped; reports for existing wards continue in the same transaction.
This also applies to scheduled migrations. The tool does not create or alter
the database schema.

The SSH tunnel closes on normal completion, migration failure, or handled
interruption. A forwarding port already in use aborts the run; choose another
free `TARGET_DB_PORT` or close the existing tunnel. A generic database failure
requires checking database credentials, connectivity, TLS, schema, and grants.
The script intentionally avoids printing database error details that may
contain report content or credentials.

This manual historical copy is independent of the existing outbox delivery
worker. It does not enqueue, acknowledge, or modify outbox records.
