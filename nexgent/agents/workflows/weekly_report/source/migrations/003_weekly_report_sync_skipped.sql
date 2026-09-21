-- Apply to the LOCAL report database before deploying the skip-aware sync worker.
-- Keep existing blocked deliveries for explicit operator retry and revalidation.
BEGIN;
ALTER TABLE ansimk.weekly_report_sync_outbox
    DROP CONSTRAINT weekly_report_sync_outbox_status_check;
ALTER TABLE ansimk.weekly_report_sync_outbox
    ADD CONSTRAINT weekly_report_sync_outbox_status_check
    CHECK (status IN ('pending', 'running', 'delivered', 'blocked', 'skipped'));
COMMIT;
