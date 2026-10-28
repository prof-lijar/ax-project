# Migrate guardian-action template IDs

Configuration update (2026-10-27): all agent configuration now comes from
`agents/.env`; see [unified environment](../../docs/unified-environment.md).
Production migration uses `LIVE_PROD_*` and development migration uses
`LIVE_DEV_*`. Older per-tool env files are no longer read.

Date: 2026-10-19

Recalculate legacy guardian-action item IDs in saved weekly reports using the
current reporter selection policy. This is an ID-only migration: it preserves
card text, summaries, metrics, item order, and every other JSON field. Changed
rows also receive a fresh `updated_at`. No reports are inserted or deleted.

The default is **read-only preview**. `--write` explicitly enables updates.
Local and live reports are calculated independently from their own saved data;
local report IDs are never used to identify live rows.

## Commands

From the `agents` directory, preview both databases:

```bash
bash playground/migrate-guardian-template-ids/run.sh --target both
```

After reviewing the preview counts and artifact, apply:

```bash
bash playground/migrate-guardian-template-ids/run.sh --target both --write
```

Verify by repeating the preview. `would_update` and `blocked` should both be
zero after a complete migration, provided no legacy reports were added.

Run a single target or week:

```bash
bash playground/migrate-guardian-template-ids/run.sh --target local
bash playground/migrate-guardian-template-ids/run.sh --target live --week-start 2026-09-28
bash playground/migrate-guardian-template-ids/run.sh --target live --week-start 2026-09-28 --write
bash playground/migrate-guardian-template-ids/run.sh --help
```

`--target` defaults to `local`. An omitted week selects all saved reports.
`--week-start` must be a Monday. `--output-dir PATH` changes the private artifact
directory. Python can be run directly when a live tunnel is already open:

```bash
.venv/bin/python playground/migrate-guardian-template-ids/migrate.py --target live
```

## How IDs are calculated

The script scans saved `weekly-report-v5` reports. It changes only string IDs
under `guardian_actions.items` that do not start with the literal `GUI_` prefix.
Already-prefixed IDs, item nulls, the parent ID, and empty states are preserved.
In particular, the approved complete-data-absence power-check card keeps its
null ID. This migration does not repair previously existing empty-state policy
or re-evaluate already-prefixed IDs.

For each candidate report:

1. Recompute activity and remote-control classifications from saved current and
   previous totals using the current activity algorithm. Require saved statuses
   to agree with those computed classifications.
2. Resolve environment status/variant and device status/kind from their saved
   status and tag using the current policy's exact label catalog. The report
   JSON does **not** retain daily directional environment counts or the original
   device power-pattern count, so it cannot independently recalculate these
   two underlying assessments. It uses the saved assessed conditions, without
   inventing counts or querying today's raw source data.
3. Use the same `select_guardian_guides` function as normal report generation,
   including status/trend requirements, device precedence, environment variant
   eligibility, score/record gates, priority, and the three-card cap.
4. Match each legacy card's title and action tag to an eligible current guide
   and use that guide's template ID. The old ID does not select its replacement.
   For example, a card about decreased activity with verified decreased/RISK
   activity gets `GUI_ACT_RISK_01` even if its old ID was incorrectly labeled
   `ACT_RISK_04`. Old approved description wording is preserved.

Unknown conditions, malformed data, invalid periods, inconsistent statuses,
unsupported versions, or a legacy card that is not selected by current policy
are recorded as `blocked`. No partial changes are made within a report. **Any
blocked report prevents all writes for that target.** The preview artifact lists
its report ID, ward ID, week, and reason. Review or regenerate that report; the
script has no force-prefix or skip-conflict option.

This verifies and corrects the IDs of existing legacy cards; it does not add,
remove, reorder, or regenerate cards or report prose.

## Databases and connection settings

| Target | Table | Configuration |
| --- | --- | --- |
| `local` | `archive.resources_ward_weekly_report` | Existing `SOURCE_DATABASE_DSN` override, otherwise `WEEKLY_REPORT_STORAGE_DATABASE_DSN` / `ANSIMK_DATABASE_DSN` from `agents/.env` |
| `live` | `ansimk.resources_ward_weekly_report` | Existing `LIVE_PROD_DB_*` and `LIVE_PROD_SSH_*` settings in `agents/.env` |

Exported settings take precedence over dotenv files. The script reuses existing
settings without modifying them. Local mode needs no live credentials or SSH.
For `live`/`both`, the launcher opens and cleans up its own tunnel using the same
endpoint and SSH policy as the existing operator migration. It rejects a busy
forwarding port and malformed `LIVE_PROD_DB_HOST`. Help/invalid arguments do not
open SSH. Requirements: workspace `.venv`, `asyncpg`, `python-dotenv`, and, for
live access, OpenSSH and `sshpass`.

## Backup, transactions, and recovery

Each target/run creates a unique mode-0600 JSONL artifact in the ignored
`backups/` folder. Newly created directories use mode 0700. The artifact contains
planned changes and, for every update, the original selected row fields with
full original `report_data` plus the proposed JSON. It contains personal report
data and is intended for private operator recovery. Unchanged report bodies are
not copied to the artifact.

The script streams rows in batches of 250 in a repeatable-read transaction.
Preview transactions and connections are read-only. Write mode locks selected
rows; the complete plan and original values are flushed to disk before the
first UPDATE. Updates compare the database row's ID, ward ID, and original JSON.
A conflict or unexpected update count rolls back that target's transaction.
Run while ordinary report generation, copying, and delivery for the selected
weeks are idle. Existing outbox payloads and download artifacts are not changed.

`both` processes local then live. Each target is atomic, but **there is no
transaction spanning both databases**. If local commits and live subsequently
fails, rerun preview and then retry live (or both; completed ID changes are
idempotent). A final `mode: committed` receipt is emitted only after commit.
`pre_write_backup` or a `planned` record alone is not proof of commit. A lost
connection or artifact error after commit can leave completion uncertain;
inspect with preview before retrying.

For an undo, the original JSON and proposed JSON in the artifact permit a
report-ID/ward-ID-scoped restoration guarded by equality with the proposed JSON.
Do not restore a row that has since been regenerated. The script does not
implicitly restore or replay artifacts; each execution makes a fresh plan.

Exit status: `0` for a successful preview/write with no conflicts, `2` for a
preview with blocked reports, and `1` for execution failure (including blocked
write mode). In `both` mode, a failure does not undo an earlier target's commit.

## Validation

- 101 focused migration, guardian-policy, and rendering tests passed. Coverage
  includes all 14 legacy mappings, condition mismatches, ID-only preservation,
  no-data nulls, idempotency, read-only previews, backup-before-write, target
  table routing, blocked writes, and rollback on a failed update.
- Offline analysis of the exported 15,507 legacy reports found all eligible,
  with zero conflicts.
- Local read-only preview scanned 46,276 reports: 15,507 updates, 30,769 unchanged,
  zero blocked. Live read-only preview scanned 46,239 reports: 14,961 updates,
  31,278 unchanged, zero blocked. The two databases contain different saved
  report sets; each was evaluated independently.
- Changed Python files pass Ruff; shell syntax, LangGraph (four graphs), Compose
  rendering, and the weekly-reporter skill validator pass. Repository-wide Ruff
  reports two pre-existing import/export sorting issues in
  `packages/integrations/src/ax_integrations/__init__.py` and
  `tests/unit/test_rag_chat_graph.py`.
- The full test suite stalled after early progress and was stopped by a
  60-second timeout; full-suite completion is unverified. The 101 focused tests
  above completed normally.
- No local or live database updates were executed during implementation.
