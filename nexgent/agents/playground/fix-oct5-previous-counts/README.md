# One-time October 5–11 previous-count correction

This standalone program matches every saved production report for **October
5–11, 2026** with the same ward's saved **September 28–October 4, 2026** report.
It copies the September report's actual activity and remote-control counts into
the October report's previous-week counts, then recalculates the percentages
and display strings using the reporter's existing policy. Dates are fixed in
the program to keep this a one-time operation.

It reads and updates production `ansimk.resources_ward_weekly_report` directly.
It does not regenerate reports, call an LLM, or invoke the normal migration.
Current-week counts, classifications, scores, summaries, guardian actions, all other JSON fields,
and the September reports remain unchanged. Updated rows receive a new
`updated_at`. No rows are created or deleted.

For ward 12007, if the stored reports contain the investigated values:

| Metric | October actual (preserved) | Previous before | Previous after | New ratio |
| --- | ---: | ---: | ---: | ---: |
| Activity | 8,193 | 6,833 | 6,009 | 136.3% |
| Remote control | 3,175 | 2,747 | 2,339 | 135.7% |

## Commands

From the `agents` workspace root, preview:

```bash
bash playground/fix-oct5-previous-counts/run.sh
```

Inspect the JSON artifact path printed by the preview. Its `plans` array lists
every selected ward, before/after counts, ratios, classifications, and whether
it can be updated. No report names or full report content are printed to the
terminal. To commit eligible corrections:

```bash
bash playground/fix-oct5-previous-counts/run.sh --write
```

Verify by running preview again:

```bash
bash playground/fix-oct5-previous-counts/run.sh
```

`would_update` should be zero if the saved reports have not changed after the
write. `unchanged` means both the counts and their derived display/percentage
fields already match. Check `skipped` separately; zero updates does not mean
every ward was corrected.

Show options without opening a connection:

```bash
bash playground/fix-oct5-previous-counts/run.sh --help
```

## Skipped rows

Both signals must be eligible before a ward is updated. The program skips and
prints the ward ID when:

- `missing_baseline`: no saved September 28 report exists for that ward.
- `invalid_report`: the dates, numeric fields, or required structure are
  invalid. Missing fields are not treated as zero.

These rows remain unchanged, including both comparison metrics. A zero/null
denominator uses the reporter's unavailable-comparison policy.

Classification or trend changes do **not** block copying the counts. The
one-time correction updates numeric comparison fields only, as requested.
Existing classifications, summaries, and guardian guidance are preserved even
if they no longer agree with the corrected comparison. The plan's calculated
before/after classifications are informational, not fields written to the report.

For the preview with 6,654 reports (3,617 updates, 1,066 unchanged, 1,929
previously blocked by summary review, and 42 missing baselines), the revised
program should show **5,546 updates, 1,066 unchanged, and 42 skipped**, provided
no report data has changed. `needs_summary_review` is no longer a skip reason.

Exit status is `0` for a complete preview/write with no skipped wards, `2` when
some wards are skipped (eligible updates still commit with `--write`), and `1`
on failure. A missing October report is not created and is outside the selected
set. The printed `reports` count refers to saved October reports, not the ward roster.

## Connection, backup, and recovery

The independent launcher opens its own SSH tunnel, runs `fix.py`, and closes
the tunnel. It reads the already-configured connection settings from
`playground/weekly-reporter/.env`; it does not edit that file or the existing
migration scripts. Exported environment variables take precedence. It requires
the workspace `.venv`, `asyncpg`, `python-dotenv`, OpenSSH, and `sshpass`.
`TARGET_DB_HOST` must be `127.0.0.1` or `localhost`. The SSH destination and
database forwarding endpoint match the existing operator connection. A port
already in use aborts the command; choose another `TARGET_DB_PORT` if needed.

Every run creates a unique private JSON artifact under this directory's ignored
`backups/` folder (or `--output-dir PATH`). It includes full original rows for
both weeks and the plan, so it contains personal report data: retain it as a
private operator backup. Files are created with mode `0600`; new directories
use `0700`. Existing backups are never overwritten. On `--write`, the artifact
is flushed to disk before any report updates occur.

All eligible updates share one production transaction. Both weeks are read
from one repeatable-read snapshot and locked against concurrent row updates
in write mode. Any failed update rolls back the transaction. Write mode builds
a fresh plan; it does not apply a potentially stale preview file. Run while
generation, migration, and report delivery for this week are idle.

The final `mode: committed` message appears only after commit succeeds. A backup
marked `pre_write_backup` is not proof of a commit. If a connection fails during
commit, run preview again to determine the resulting state before retrying.
Retries are idempotent. To undo a committed correction, use that run's original
October `report_data` values in a separately reviewed, ward/week-scoped recovery;
do not overwrite reports that have since been regenerated.

**Local archive reports and generated download artifacts are not updated.** A
later ordinary regeneration or migration of this week can overwrite these live
corrections. This tool does not change the scheduler, calculation policy, or
normal delivery behavior.
