# Weekly report production delivery

Status: implemented; production activation requires the local migration and
operator-supplied SSH/database configuration. No production writes are part of
implementation validation. The operator confirmed that local and production
ward IDs identify the same people. SSH forwarding must still be verified.

## Ownership and guarantees

`apps/workers/weekly_report_sync.py` runs the deterministic sync worker. The
workflow-owned `workflows/weekly_report/sync/` module owns settings, immutable
payloads, the local outbox, target SQL, retries, and conflict policy. The worker
has no model, source API, graph, scheduler, or ZIP dependency.

The production generation writer saves each frontend report and its delivery
payload in the **same local report-database transaction**, in the existing
bounded batches. The outbox is not in the separate bulk-job database. An enqueue
failure rolls back report storage. An immutable, versioned JSON text payload
and SHA-256 checksum preserve the original content even if local report rows
change; text preserves JSON number encoding through PostgreSQL round trips.
Identical payloads deduplicate through their checksum. No report ID is copied.

Only a writer explicitly configured with `WEEKLY_REPORT_DEPLOYMENT=production`
and `WEEKLY_REPORT_SYNC_ENQUEUE=true` enqueues. Existing development settings
default to no enqueue. UI requests with `persist_reports=false` never invoke the
writer. The production overlay sets the flags on the generation worker only;
do not place production flags in the shared `agents/.env`.

Delivery eligibility means a report was successfully saved by the production
writer. Existing partial/cancelled bulk finalizations can save completed reports;
those saved reports are also eligible. This does not wait for the separate job
metadata transaction to mark the job terminal. Generation and delivery status
are independent. Deployment enables future deliveries; it never sweeps old
local rows, which may include development data.

One worker delivers one report transaction at a time, processing up to 100
ready records before polling again. A SQL claim uses row locking and a UUID
lease token; the lease expires after 120 seconds. Each target operation has a
60-second deadline, with shorter connection, statement, and lock timeouts.
Restart or cancellation leaves a reclaimable lease. A stale lease token cannot
acknowledge another worker's claim.

The target writer inserts missing ward/week rows. Identical content is a no-op,
including timestamps; different content becomes `content_conflict` and is never
overwritten. A concurrent insert is verified after `ON CONFLICT DO NOTHING`.
Target commit precedes local acknowledgement, so a crash in between causes a
safe duplicate delivery. This is at-least-once delivery, not a distributed
transaction or an atomic publication of an entire week. Other applications
must not delete or rewrite delivered report rows without an agreed policy.

Target FK existence is checked, but does not establish cross-database identity;
`WEEKLY_REPORT_SYNC_WARD_IDS_VERIFIED=true` records the operator's identity
verification. Current deployment supports identical ward IDs only. Schema and
content validation happen before insertion. Missing wards, content conflicts,
invalid payloads, and permanent database errors block that delivery. Network and
transient database failures retry after 30, 60, 120 seconds, up to one hour.
After eight attempts, including expired crash leases, delivery is blocked for
explicit retry. Failure of one delivery does not stop other reports.

Logs and status contain only delivery IDs, counts, outcomes, and safe error
codes. Outbox payloads are private care data; restrict database access and apply
local database backup/retention policy. ZIP cleanup does not delete deliveries.
Delivered entries are retained for audit/deduplication; no automatic purge is
introduced. Pending and blocked entries must not be purged.

## Deployment

Use `compose.weekly-report-sync.prod.yaml` as an overlay on the parent
`compose.prod.yaml`. This keeps all implementation files inside `agents/` and
keeps the service absent from the development stack. Use both Compose files for
subsequent production operations so the enqueue flags and services remain set.

1. Apply `workflows/weekly_report/source/migrations/002_weekly_report_sync_outbox.sql`
   to the **local report database**, using your migration role, before rebuilding
   the generation worker with enqueue enabled. The target requires the existing
   report schema and ward/week unique constraint; no target migration is needed.
2. Grant the generation role INSERT and SELECT on the outbox, and USAGE on its
   identity sequence, alongside its existing report-table permissions. Grant
   the local sync role SELECT on the outbox and UPDATE only on `status`,
   `attempts`, `next_attempt_at`, `lease_token`, `lease_until`, `error_code`, and
   `delivered_at`. Neither role should update the immutable payload columns.
3. Give the production sync role schema USAGE, SELECT on the ward table,
   SELECT/INSERT on the report table, and USAGE on its identity sequence. It
   does not need UPDATE, DELETE, DDL, or access to source metrics.
4. Copy `apps/weekly_report_tunnel/sync.env.example` to
   `/etc/nexgent/weekly-report-sync.env`, mode 0600, and populate its values.
   Percent-encode reserved characters in DSN credentials. The local DSN points
   to the same database used by the production generation writer, using the
   separate sync role. The target DSN is explicit and has no local fallback.
5. Install the SSH private key, verified `known_hosts`, and production DB CA
   at the paths in the overlay. Verify the server host key independently.
   The SSH account should permit forwarding only to the required DB host/port;
   it needs no interactive shell or agent forwarding. The key is mounted only
   into the tunnel container; production DB credentials only into the sync
   container. The tunnel receives SSH host/user and target address, not DSNs.
6. The target DSN host must equal `WEEKLY_REPORT_TARGET_HOST` and match the DB
   certificate, with port **15432**. A dedicated Docker bridge aliases that
   hostname to the tunnel. The tunnel resolves the actual destination from the
   SSH server. Keep `sslmode=verify-full` and the supplied CA: SSH alone does not
   protect the hop from the Linux server to the database. No tunnel host port
   is published. Only the sync worker joins the tunnel bridge; bridge egress
   permits SSH. Tunnel health checks establish listener readiness, not DB
   readiness; worker failures remain durable when the ultimate DB is down.

From the parent `nexgent/` directory, use:

```sh
docker compose --env-file /etc/nexgent/weekly-report-sync.env \
  -f compose.prod.yaml -f agents/compose.weekly-report-sync.prod.yaml \
  config --quiet

docker compose --env-file /etc/nexgent/weekly-report-sync.env \
  -f compose.prod.yaml -f agents/compose.weekly-report-sync.prod.yaml \
  up -d --build weekly-report-worker weekly-report-sync-tunnel weekly-report-sync
```

If the base production stack relies on additional Compose interpolation files,
pass those first with additional `--env-file` arguments. The sync env file is
also read into the sync container. The generation worker retains its existing
local source/model configuration and gets no sync target DSN.

## Operations and recovery

Use the same Compose prefix above with `exec weekly-report-sync` followed by:

```sh
/app/.venv/bin/python -m apps.workers.weekly_report_sync check
/app/.venv/bin/python -m apps.workers.weekly_report_sync status
/app/.venv/bin/python -m apps.workers.weekly_report_sync dry-run
/app/.venv/bin/python -m apps.workers.weekly_report_sync run-once
/app/.venv/bin/python -m apps.workers.weekly_report_sync retry DELIVERY_ID
```

`check` opens read-only transactions against both databases and verifies the
outbox columns, target tables, and an immediate unique ward/week index. It
performs no probe inserts and does not certify INSERT/sequence permissions or
compatibility of report content. `dry-run` runs this readiness check first,
even when its queue is empty. Both commands return nonzero if readiness fails.

`status` reports total counts and the first 100 outstanding IDs. `dry-run`
validates up to 100 pending/blocked payloads with read-only target transactions;
it does not claim, insert, or acknowledge. For a controlled initial dry-run,
start only the tunnel, then use `run --rm --no-deps weekly-report-sync` with the
Python command above instead of starting `serve`. An empty-queue dry-run verifies connectivity and schema readiness; enqueue a
known production report to also validate report compatibility.

`run-once` processes at most 100 ready deliveries. Exit codes: 0 for success,
2 for rejected deliveries or an inapplicable retry, 1 for configuration or
connection failures outside delivery processing. The daemon logs sanitized
failures and continues polling. Monitor blocked count and outstanding delivery
age with your existing monitoring system; no new notification integration is
added.

Retrying a conflict does not authorize replacing production content. Resolve
identity/schema/connectivity issues first. Content replacement requires a
separate operator decision and procedure; this worker deliberately has no
force-overwrite mode. To pause delivery, stop `weekly-report-sync`; local
reports/outbox continue accumulating. To disable enqueue, remove the overlay's
worker flags and recreate the generation worker. Do not drop the outbox while
enqueue is enabled.

For already saved reports with retained production job artifacts, use the
existing checksum-verified [database recovery](weekly-report-database-recovery.md)
command in the production generation-worker environment with enqueue enabled.
Atomic recovery upserts the local reports and enqueues their immutable payloads
without model/source calls. Select the intended production job explicitly; no
historical backfill is automatic. `--skip-not-null` is rejected when enqueue is
enabled so partial recovery cannot silently publish an incomplete operation.

## Acceptance and validation

Required regression cases: atomic report/outbox rollback, deduplication,
development and UI exclusion, identical replay after remote commit, immutable
content conflict, missing target ward, read-only dry-run, lease fencing and
expiry, bounded retry exhaustion, and cancellation without acknowledgement.

Focused tests live in `tests/unit/test_weekly_report_sync.py` and
`tests/integration/test_weekly_report_sync_postgres.py`, alongside the existing
storage and bulk tests. Integration tests use session-local TEMP tables for source/target connections
and one uniquely named, automatically removed schema for cross-connection
locking tests. They require a disposable test database via
`WEEKLY_REPORT_TEST_DATABASE_DSN`. Never point this test setting at production.
Live SSH forwarding, target identity/schema/permissions, and production
certificate checks remain deployment gates and are not implied by local tests.


Implementation verification (2026-09-11): 75 focused sync/storage/bulk tests passed,
including PostgreSQL 18.6 on a disposable Unix-socket instance with TCP disabled.
Compose overlay rendering with placeholder configuration, LangGraph validation,
changed-file Ruff checks, and the weekly-reporter skill validator passed. The
broader suite exposed one existing scheduler contract mismatch (test expects
Monday 03:00, checked-in cron runs Monday 01:00). Repository-wide Ruff reports
pre-existing ordering issues in `packages/integrations/src/ax_integrations/__init__.py`
and `tests/unit/test_rag_chat_graph.py`. Those unrelated files were not changed.
Docker image startup, live SSH, target TLS/permissions, and production writes
were not performed.
