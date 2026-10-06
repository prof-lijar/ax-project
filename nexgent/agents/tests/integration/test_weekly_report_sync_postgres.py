"""Isolated TEMP tables only. Opt in with WEEKLY_REPORT_TEST_DATABASE_DSN."""

import asyncio
import os
from dataclasses import replace
from datetime import date
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from ax_contracts import NarrativeGenerationMetadata, WardWeeklyMetrics, WeeklyNarrative

from workflows.weekly_report.bulk import report_store
from workflows.weekly_report.domain.rendering import render_report
from workflows.weekly_report.sync import delivery, outbox
from workflows.weekly_report.tools.source_repository import _mock_delta, _snapshot


@pytest.fixture
def report_record():
    current, previous = _snapshot(101, current=True), _snapshot(101, current=False)
    metrics = WardWeeklyMetrics(
        ward_id=101,
        display_name="테스트",
        week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10),
        current=current,
        previous=previous,
        delta=_mock_delta(current, previous),
    )
    report = render_report(
        metrics,
        WeeklyNarrative(
            headline="관찰했어요.",
            analysis_text="확인해 주세요.",
            observations=[],
            suggestions=[],
        ),
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )
    return report_store.WeeklyReportStorageRecord.from_report(report)


@pytest_asyncio.fixture
async def databases(monkeypatch):
    dsn = os.environ.get("WEEKLY_REPORT_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("WEEKLY_REPORT_TEST_DATABASE_DSN is required (test DB only)")
    root = Path(__file__).parents[2] / "workflows/weekly_report/source/migrations"
    pools = []
    try:
        for _ in range(2):
            pool = await asyncpg.create_pool(dsn, min_size=1, max_size=1)
            pools.append(pool)
            async with pool.acquire() as conn:
                await conn.execute(
                    "CREATE TEMP TABLE resources_ward (id BIGINT PRIMARY KEY)"
                )
                await conn.execute("INSERT INTO resources_ward VALUES (101)")
                for filename in (
                    "001_create_resources_ward_weekly_report.sql",
                    "002_weekly_report_sync_outbox.sql",
                    "003_weekly_report_sync_skipped.sql",
                ):
                    sql = (
                        (root / filename)
                        .read_text()
                        .replace("CREATE TABLE", "CREATE TEMP TABLE")
                    )
                    await conn.execute(sql.replace("ansimk.", "pg_temp."))
        monkeypatch.setattr(outbox, "TABLE", "pg_temp.weekly_report_sync_outbox")
        monkeypatch.setattr(
            delivery, "REPORT_TABLE", "pg_temp.resources_ward_weekly_report"
        )
        monkeypatch.setattr(delivery, "WARD_TABLE", "pg_temp.resources_ward")
        monkeypatch.setattr(
            report_store,
            "_UPSERT_REPORT_SQL",
            report_store._UPSERT_REPORT_SQL.replace("archive.", "pg_temp."),
        )
        yield pools
    finally:
        for pool in pools:
            await pool.close()


async def save(pool, records, enabled=True):
    store = report_store.AsyncpgWeeklyReportStore(
        report_store.WeeklyReportStorageSettings(
            dsn="test", enqueue_sync=enabled, batch_size=1
        )
    )
    store._pool = pool

    async def stream():
        for record in records:
            yield record

    return await store.upsert_reports(stream())


@pytest.mark.asyncio
async def test_atomic_enqueue_dedup_and_failure_rollback(databases, report_record):
    local, _ = databases
    await save(local, [report_record], enabled=False)
    assert (
        await local.fetchval("SELECT count(*) FROM pg_temp.weekly_report_sync_outbox")
        == 0
    )
    await save(local, [report_record, report_record])
    assert (
        await local.fetchval("SELECT count(*) FROM pg_temp.weekly_report_sync_outbox")
        == 1
    )
    modified = replace(report_record, weekly_score=1)
    with pytest.raises(report_store.WeeklyReportStorageUnavailable):
        await save(local, [modified, replace(report_record, ward_id=999)])
    assert (
        await local.fetchval("SELECT count(*) FROM pg_temp.weekly_report_sync_outbox")
        == 1
    )
    assert (
        await local.fetchval(
            "SELECT weekly_score FROM pg_temp.resources_ward_weekly_report"
        )
        == report_record.weekly_score
    )


@pytest.mark.asyncio
async def test_replay_after_remote_commit_and_stale_ack(databases, report_record):
    local, target = databases
    await save(local, [report_record])
    queue = outbox.Outbox(local)
    first = await queue.claim()
    payload = delivery.decode_payload(first)
    await delivery.deliver(target, payload)
    before = await target.fetchrow("SELECT * FROM pg_temp.resources_ward_weekly_report")
    # Simulate crash after remote COMMIT and before local acknowledgement.
    await local.execute(
        "UPDATE pg_temp.weekly_report_sync_outbox SET lease_until=NOW()-INTERVAL '1 second'"
    )
    reclaimed = await queue.claim()
    await queue.finish(first["id"], first["lease_token"])
    assert (await queue.status())["counts"] == {"running": 1}
    assert (
        await delivery.deliver(target, delivery.decode_payload(reclaimed))
        == "identical"
    )
    await queue.finish(reclaimed["id"], reclaimed["lease_token"])
    assert (await queue.status())["counts"] == {"delivered": 1}
    after = await target.fetchrow("SELECT * FROM pg_temp.resources_ward_weekly_report")
    assert dict(before) == dict(after)


@pytest.mark.asyncio
async def test_dry_run_conflict_missing_ward_and_manual_retry(databases, report_record):
    local, target = databases
    await save(local, [report_record])
    queue = outbox.Outbox(local)
    row = (await queue.preview(100))[0]
    payload = delivery.decode_payload(row)
    assert await delivery.deliver(target, payload, dry_run=True) == "missing"
    assert (await queue.status())["counts"] == {"pending": 1}
    assert (
        await target.fetchval(
            "SELECT count(*) FROM pg_temp.resources_ward_weekly_report"
        )
        == 0
    )
    await target.execute("DELETE FROM pg_temp.resources_ward")
    result = await delivery.process_one(queue, target)
    assert result == {
        "delivery_id": row["id"],
        "outcome": "skipped_missing_ward",
        "ward_id": 101,
        "week_start_date": "2026-08-03",
    }
    assert (await queue.status())["counts"] == {"skipped": 1}
    assert (await queue.status())["outstanding"] == []
    assert await queue.claim() is None
    skipped = await local.fetchrow("SELECT * FROM pg_temp.weekly_report_sync_outbox")
    assert skipped["error_code"] == "missing_ward"
    assert skipped["delivered_at"] is None
    assert skipped["lease_token"] is None
    await target.execute("INSERT INTO pg_temp.resources_ward VALUES (101)")
    assert await queue.retry(row["id"])
    await delivery.process_one(queue, target)
    await target.execute(
        "UPDATE pg_temp.resources_ward_weekly_report SET report_data='{}'"
    )
    with pytest.raises(delivery.DeliveryError, match="content_conflict"):
        await delivery.deliver(target, payload)
    assert (
        await target.fetchval(
            "SELECT report_data FROM pg_temp.resources_ward_weekly_report"
        )
        == "{}"
    )


@pytest.mark.asyncio
async def test_bounded_retries_and_exhausted_crash_lease(databases, report_record):
    local, _ = databases
    await save(local, [report_record])
    queue = outbox.Outbox(local, max_attempts=2)
    first = await queue.claim()
    await queue.finish(
        first["id"],
        first["lease_token"],
        error_code="connection_unavailable",
        retryable=True,
    )
    assert await queue.claim() is None  # Backoff is durable.
    await local.execute(
        "UPDATE pg_temp.weekly_report_sync_outbox SET next_attempt_at=NOW()"
    )
    second = await queue.claim()
    assert second["attempts"] == 2
    await local.execute(
        "UPDATE pg_temp.weekly_report_sync_outbox SET lease_until=NOW()-INTERVAL '1 second'"
    )
    assert await queue.claim() is None
    assert (await queue.status())["counts"] == {"blocked": 1}


@pytest.mark.asyncio
async def test_concurrent_claims_do_not_duplicate_a_lease(databases, report_record):
    local, _ = databases
    await save(local, [report_record])
    queue = outbox.Outbox(local)
    claims = await asyncio.gather(queue.claim(), queue.claim())
    assert sum(row is not None for row in claims) == 1


@pytest.mark.asyncio
async def test_outbox_rejection_rolls_back_local_report(databases, report_record):
    local, _ = databases
    await local.execute(
        "ALTER TABLE pg_temp.weekly_report_sync_outbox "
        "ADD CONSTRAINT reject_delivery CHECK (false) NOT VALID"
    )
    with pytest.raises(report_store.WeeklyReportStorageUnavailable):
        await save(local, [report_record])
    assert (
        await local.fetchval(
            "SELECT count(*) FROM pg_temp.resources_ward_weekly_report"
        )
        == 0
    )


@pytest.mark.asyncio
async def test_claim_skips_rows_locked_by_another_connection(monkeypatch):
    from uuid import uuid4

    dsn = os.environ.get("WEEKLY_REPORT_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("WEEKLY_REPORT_TEST_DATABASE_DSN is required (test DB only)")
    schema = "test_weekly_sync_" + uuid4().hex
    migration = (
        Path(__file__).parents[2]
        / "workflows/weekly_report/source/migrations/002_weekly_report_sync_outbox.sql"
    ).read_text()
    async with asyncpg.create_pool(dsn, min_size=2, max_size=2) as pool:
        await pool.execute(f"CREATE SCHEMA {schema}")
        try:
            await pool.execute(migration.replace("ansimk.", f"{schema}."))
            monkeypatch.setattr(outbox, "TABLE", f"{schema}.weekly_report_sync_outbox")
            async with pool.acquire() as conn:
                await outbox.enqueue(
                    conn,
                    [
                        (101, date(2026, 8, 3), date(2026, 8, 9), 90, "GOOD", "{}"),
                        (102, date(2026, 8, 3), date(2026, 8, 9), 90, "GOOD", "{}"),
                    ],
                )
                async with conn.transaction():
                    await conn.fetchrow(
                        f"SELECT id FROM {outbox.TABLE} ORDER BY id LIMIT 1 FOR UPDATE"
                    )
                    claimed = await asyncio.wait_for(outbox.Outbox(pool).claim(), 2)
                    assert claimed["id"] == 2
            assert (await outbox.Outbox(pool).claim())["id"] == 1
            assert await outbox.Outbox(pool).claim() is None
        finally:
            # Drop only the randomly named test schema created by this test.
            await pool.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.mark.asyncio
async def test_readiness_checks_empty_databases_without_writing(databases):
    local, target = databases
    await outbox.Outbox(local).check()
    await delivery.check_target(target)
    assert (
        await local.fetchval("SELECT count(*) FROM pg_temp.weekly_report_sync_outbox")
        == 0
    )
    assert (
        await target.fetchval(
            "SELECT count(*) FROM pg_temp.resources_ward_weekly_report"
        )
        == 0
    )


@pytest.mark.asyncio
async def test_readiness_rejects_missing_unique_key(databases):
    _, target = databases
    constraint = await target.fetchval(
        "SELECT conname FROM pg_constraint WHERE conrelid="
        "'pg_temp.resources_ward_weekly_report'::regclass AND contype='u'"
    )
    await target.execute(
        f'ALTER TABLE pg_temp.resources_ward_weekly_report DROP CONSTRAINT "{constraint}"'
    )
    with pytest.raises(delivery.DeliveryError, match="target_unique_key_missing"):
        await delivery.check_target(target)


@pytest.mark.asyncio
async def test_readiness_rejects_missing_local_migration(databases):
    local, _ = databases
    await local.execute("DROP TABLE pg_temp.weekly_report_sync_outbox")
    with pytest.raises(asyncpg.UndefinedTableError):
        await outbox.Outbox(local).check()


@pytest.mark.asyncio
async def test_skip_is_terminal_and_next_valid_report_delivers(
    databases, report_record
):
    local, target = databases
    await local.execute("INSERT INTO pg_temp.resources_ward VALUES (102)")
    await target.execute("DELETE FROM pg_temp.resources_ward")
    await target.execute("INSERT INTO pg_temp.resources_ward VALUES (102)")
    await save(local, [report_record, replace(report_record, ward_id=102)])
    queue = outbox.Outbox(local)
    row = (await queue.preview(100))[0]
    payload = delivery.decode_payload(row)
    assert (
        await delivery.deliver(target, payload, dry_run=True) == "skipped_missing_ward"
    )
    assert (await queue.status())["counts"] == {"pending": 2}
    assert (await delivery.process_one(queue, target))[
        "outcome"
    ] == "skipped_missing_ward"
    assert (await delivery.process_one(queue, target))[
        "outcome"
    ] == "inserted_or_identical"
    assert (await queue.status())["counts"] == {"skipped": 1, "delivered": 1}
    assert await queue.claim() is None
    assert (
        await target.fetchval(
            "SELECT ward_id FROM pg_temp.resources_ward_weekly_report"
        )
        == 102
    )


@pytest.mark.asyncio
async def test_stale_skip_cannot_finish_another_lease(databases, report_record):
    local, _ = databases
    await save(local, [report_record])
    queue = outbox.Outbox(local)
    first = await queue.claim()
    await local.execute(
        "UPDATE pg_temp.weekly_report_sync_outbox SET lease_until=NOW()-INTERVAL '1 second'"
    )
    second = await queue.claim()
    await queue.finish(first["id"], first["lease_token"], skipped=True)
    assert (await queue.status())["counts"] == {"running": 1}
    await queue.finish(second["id"], second["lease_token"], skipped=True)
    assert (await queue.status())["counts"] == {"skipped": 1}


@pytest.mark.asyncio
async def test_skip_migration_preserves_existing_blocked_deliveries(
    databases, report_record
):
    local, _ = databases
    await save(local, [report_record])
    queue = outbox.Outbox(local)
    row = await queue.claim()
    await queue.finish(row["id"], row["lease_token"], error_code="missing_ward")
    await local.execute(
        "ALTER TABLE pg_temp.weekly_report_sync_outbox "
        "DROP CONSTRAINT weekly_report_sync_outbox_status_check; "
        "ALTER TABLE pg_temp.weekly_report_sync_outbox "
        "ADD CONSTRAINT weekly_report_sync_outbox_status_check "
        "CHECK (status IN ('pending', 'running', 'delivered', 'blocked'))"
    )
    migration = (
        (
            Path(__file__).parents[2]
            / "workflows/weekly_report/source/migrations/003_weekly_report_sync_skipped.sql"
        )
        .read_text()
        .replace("ansimk.", "pg_temp.")
    )
    before = await local.fetchrow("SELECT * FROM pg_temp.weekly_report_sync_outbox")
    with pytest.raises(outbox.OutboxSchemaError, match="outbox_skip_migration_missing"):
        await queue.check()
    await local.execute(migration)
    await queue.check()
    assert dict(
        await local.fetchrow("SELECT * FROM pg_temp.weekly_report_sync_outbox")
    ) == dict(before)
    assert await queue.retry(row["id"])
    retried = await queue.claim()
    await queue.finish(retried["id"], retried["lease_token"], skipped=True)
    assert (await queue.status())["counts"] == {"skipped": 1}
