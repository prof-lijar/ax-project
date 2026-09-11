-- Apply only to the LOCAL report database, before enabling production enqueue.
-- Immutable payloads survive report updates and ZIP retention.
CREATE TABLE ansimk.weekly_report_sync_outbox (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload TEXT NOT NULL CHECK (jsonb_typeof(payload::jsonb) = 'object'),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'delivered', 'blocked')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at TIMESTAMPTZ,
    UNIQUE (payload_sha256),
    CHECK ((status = 'running') = (lease_token IS NOT NULL AND lease_until IS NOT NULL))
);
CREATE INDEX weekly_report_sync_ready_idx
    ON ansimk.weekly_report_sync_outbox (next_attempt_at, id)
    WHERE status = 'pending';
CREATE INDEX weekly_report_sync_lease_idx
    ON ansimk.weekly_report_sync_outbox (lease_until)
    WHERE status = 'running';
