# October 26–November 1 previous-count correction

This one-time tool copies each ward's saved **October 19–25, 2026 actual
motion and remote-control counts** into its **October 26–November 1, 2026
previous-week counts**. Dates are fixed; it never re-sums daily observations.

It defaults to both local `archive.resources_ward_weekly_report` and production
`ansimk.resources_ward_weekly_report`. Each target uses its own saved preceding
report as the baseline. Preview before applying; if baseline values differ
between databases, resolve that difference before expecting identical results.

From the `agents` workspace, preview, apply, then verify:

```bash
bash playground/fix-oct26-previous-counts/run.sh
bash playground/fix-oct26-previous-counts/run.sh --write
bash playground/fix-oct26-previous-counts/run.sh
```

Use `--target local`, `--target prod`, or `--target both` (default) to select
connections. `--help` opens no connection. Local-only mode needs no SSH or
production credentials. Connections use unified `agents/.env`: local storage
DSN first, then `ANSIMK_DATABASE_DSN`; production uses `LIVE_PROD_*` and its
own SSH tunnel. An occupied tunnel port aborts; use `LIVE_PROD_TUNNEL_PORT`
with an available port if needed. The launcher copies existing SSH host keys
into its temporary directory rather than modifying global configuration.

For each signal, only these report JSON fields change:

- `metrics.previous_week`, copied from the prior report's `metrics.current_week`;
- `metrics.previous_week_display`;
- `metrics.comparison_percent` and `metrics.comparison_display`.

Changed rows receive a new `updated_at`. Current counts, prior reports,
classifications, descriptions, summaries, scores, guardian actions and other
fields are preserved. Existing text and classifications can disagree with the
corrected percentages. The preview records calculated before/after
classifications; those classifications are informational and are not written.
No LLM calls, regeneration, notifications, inserts or deletes occur. Existing
ZIP/download artifacts are not updated.

For ward 13554, the investigated correction is:

| Metric | Current (preserved) | Previous before | Previous after | Comparison after |
| --- | ---: | ---: | ---: | ---: |
| Motion | 2,710 | 3,002 | 2,278 | 119.0% |
| Remote control | 1,967 | 1,606 | 1,123 | 175.2% |

Both signals must have valid structure. Missing prior reports are skipped as
`missing_baseline`; malformed counts, mismatched wards or dates are skipped as
`invalid_report`. Null remains unavailable, zero is copied as zero, and zero
or unavailable denominators produce an unavailable ratio. Missing fields are
invalid, not zero. A missing current-week report is outside the selected set;
this tool does not create one. Skipped wards are identified in output and the
private artifact. Exit code 2 means eligible changes completed but some wards
were skipped; 0 means no skips; 1 means failure.

Each run saves full original rows for both weeks plus its correction plan in
ignored `backups/local/` and `backups/prod/` (override with `--output-dir`).
Files are private mode 0600 and never overwritten. The write backup is flushed
before any UPDATE. Keep these backups for recovery; they contain personal
report data and must not be committed or shared.

Each database has its own repeatable-read transaction. Write mode locks both
weeks, uses original-JSON conflict checks and verifies complete patched JSON
before commit. Local commits first; production commits second. There is no
cross-database atomicity. If production fails after local commits, preserve the
local receipt and rerun preview, then retry the failed target. A
`pre_write_backup` artifact alone does not prove a commit; only the target's
`mode: committed` output confirms it. Repeating an unchanged correction makes
zero updates. Verification should show `would_update: 0`; inspect skips
separately.

Run between generation/migration jobs. Later regeneration can replace these
values; deploy the saved-count source policy before regenerating this week.
For rollback, use the corresponding target's original October 26 JSON in a
separately scoped recovery with a check that the corrected row has not since
changed. Do not replace an entire table or overwrite subsequent reports.

Tests:

```bash
.venv/bin/pytest tests/unit/test_oct26_previous_count_fix.py
```

## Applied and verified on 2026-11-02

The operator authorized all wards for this week. Local and production previews
had identical plans. Both target transactions committed successfully:

| Target | Selected reports | Updated | Already matched | Missing baseline |
| --- | ---: | ---: | ---: | ---: |
| Local archive | 6,297 | 5,571 | 717 | 9 |
| Production | 6,297 | 5,571 | 717 | 9 |

The subsequent read-only previews each reported `would_update: 0`,
`unchanged: 6288`, and `missing_baseline: 9`. Exit code 2 was expected because
of the nine skips; both commits were confirmed in the log. Comparing the
complete before/after snapshots independently verified 5,571 changed rows per
target, unchanged baseline rows, and preservation of all fields except the
four allowed comparison fields per signal and `updated_at`.

Ward 13554 was verified at 2,278/1,123 previous counts and 119.0%/175.2%
comparisons in both databases. The preview identified 1,969 reports whose
calculated classifications would change; stored classifications and narrative
were deliberately preserved under this counts-only operation.

Private commit receipts: `backups/apply-20261102.log`.
Verification receipts: `backups/verify-20261102.log`.
Pre-write backups:

- `backups/local/20261102T064813Z-ac719d88f2b54a4881891b5a98f47af9.json`
- `backups/prod/20261102T064826Z-fd6bcf6787ec4510939478b997907d02.json`

All artifacts are ignored by Git. The 27 correction tests, changed-file Ruff,
shell syntax, CLI help, LangGraph validation, Compose rendering and skill
validation passed. The previously documented unrelated full-suite failures
and stalls remain outside this correction.

