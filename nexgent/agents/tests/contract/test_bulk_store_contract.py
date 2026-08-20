from inspect import getsource

from ax_persistence.bulk import SCHEMA_SQL, AsyncpgBulkJobStore


def test_bulk_schema_has_idempotency_and_recoverable_leases() -> None:
    assert "UNIQUE (job_kind, idempotency_key)" in SCHEMA_SQL
    assert "FOR UPDATE SKIP LOCKED" in getsource(AsyncpgBulkJobStore.claim_items)
    assert "producer_lease_expires_at" in SCHEMA_SQL
    assert "finalizer_lease_expires_at" in SCHEMA_SQL
