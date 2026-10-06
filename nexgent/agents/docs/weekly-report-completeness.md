# Every ward receives a weekly report

Date: 2026-09-21

The operator requires the weekly report count to equal the `resources_ward`
count, including wards without weekly records. The generation notice
`문구 생성이 어려워 검증된 안내 문구로 자동 대체됨` must not appear in
guardian reports.

Production delivery exception (2026-09-21): after complete local generation,
reports for wards absent from the production roster are logged and skipped.
Scheduled migration counts them; the optional outbox worker persists a terminal
skip. This does not permit dropping source wards or incomplete local artifacts.
See [production delivery](weekly-report-production-sync.md).

## Acceptance and implementation

- Discover every ward from `archive.resources_ward` in ID order. No daily-summary,
  evaluation, or dispatch record is required for membership. Missing data uses
  the existing unavailable displays without inventing measurements.
- Retain one report per ward when the model fails, times out, or returns invalid
  text. Use the existing deterministic fallback first. A fallback prose-policy
  failure uses a fixed neutral summary referring to the unchanged detail
  sections. This final summary contains no personal name, measurements,
  interpretation, or generation-failure message; it is not passed through the
  model-prose requirements for name and material-topic coverage.
- Keep generation mode/reason in report metadata. Markdown has no fallback
  note; `template_data.generation_notice` remains null for compatibility.
- Reject skipped/missing selections, wrong periods, duplicate IDs, oversized
  pages and mismatched output identity. All staged items must complete before
  report storage; exhausted artifact/data errors fail the batch without
  committing a smaller set. Cancellation does not commit partial reports.
- Keep bounded retries and atomic per-job storage. Database or filesystem
  failure remains an explicit failed job with recoverable artifacts, never a
  claim that a smaller report set satisfies the requirement.
- The scheduled pipeline continues through as many bounded jobs as needed.
  It validates completed/discovered equality and zero failed/unfinished items,
  follows continuation cursors, and migrates only after the final batch. The
  10,000 limit is per job, not per scheduled week. Generation/polling share a
  24-hour deadline; migration retains its separate one-hour deadline.
- Scheduler idempotency keys use `cron-weekly-report-all-wards-<Monday>` plus a
  cursor hash for continuation batches. Receipts use `all-wards-v1`, store batch
  IDs/counts, and do not accept old record-only receipts as full coverage.

Manual capped/ZIP-only jobs retain their explicit limits and persistence
setting. The full-week requirement is carried out by the scheduler pipeline.
No database schema changes were made. Discovery reads the live roster page by
page; simultaneous additions/deletions are not a frozen roster snapshot and
need count reconciliation after the run.

## Verification and recovery checkpoint

Read-only checks of the configured local report database found **6,600 wards**
and **6,491 wards with reports** for September 14–20, 2026: **109 missing** at
the time of the check. Production-target counts were not checked. The earlier
ward `13554` fallback failure was reproduced and fixed separately.

The regression suite passes: 653 tests, 21 optional skips. Coverage includes
actual roster SQL execution without weekly tables; 103 wards over multiple
source pages, all without data and with a broken model, producing 103 stored
reports; rejected partial artifact storage; missing selections; fallback
prose-policy failure; report notice removal; scheduler continuation beyond
10,000 reports; later-batch failure; and old-receipt replacement.
The final focused pass has 122 passing tests. Changed-file Ruff, LangGraph,
development/production Compose rendering, and skill validation pass. Whole-tree
Ruff retains the two pre-existing integrations/RAG import-order findings.

No deployment, database writes, or report migration were performed in this
session. Docker access requires interactive sudo authentication. From the
`agents/` directory, deploy the source, worker, and scheduler together:

```bash
sudo docker compose -f ../compose.prod.yaml up -d --build --no-deps weekly-report-api weekly-report-worker weekly-report-scheduler
sudo docker compose -f ../compose.prod.yaml exec -T weekly-report-scheduler python -m apps.weekly_report_scheduler.pipeline --week-start 2026-09-14
```

The second command regenerates all wards under the new policy, upserts that
week's reports locally, and runs the existing whole-week production migration.
It replaces existing reports for that week, also removing their old generation
notices. Deploy the compatibility Agent Server separately if it is still used.
Verify local archive coverage (use `ansimk` instead of `archive` when checking
the production database):

```sql
SELECT count(*) AS ward_count,
       count(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM archive.resources_ward_weekly_report r
           WHERE r.ward_id = w.id
             AND r.week_start_date = DATE '2026-09-14'
       )) AS report_count
FROM archive.resources_ward w;
```

Do not treat `--skip-not-null` recovery or a legacy `partial` job as satisfying
full coverage. If infrastructure or source contracts fail, repair the cause
and resume/recover the retained artifacts; do not fabricate reports or alter
ward identities to force the counts to match.
