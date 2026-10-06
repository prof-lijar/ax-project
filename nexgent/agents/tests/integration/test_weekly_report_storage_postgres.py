"""Run with WEEKLY_REPORT_TEST_DATABASE_DSN pointing to a test PostgreSQL DB."""

import asyncio
import json
import os
from dataclasses import replace
from datetime import date
from pathlib import Path

import asyncpg
import pytest

from workflows.weekly_report.bulk import report_store


@pytest.mark.asyncio
@pytest.mark.parametrize("timestamp_defaults", [True, False])
async def test_repeated_reports_update_the_existing_ward_week(
    monkeypatch, timestamp_defaults
) -> None:
    dsn = os.environ.get("WEEKLY_REPORT_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("WEEKLY_REPORT_TEST_DATABASE_DSN is required")

    # Session-local tables isolate this test from real ward/report data.
    async with asyncpg.create_pool(dsn, min_size=1, max_size=1) as pool:
        migration = (
            Path(__file__).parents[2]
            / "workflows/weekly_report/source/migrations"
            / "004_create_archive_ward_weekly_report.sql"
        ).read_text()
        if not timestamp_defaults:
            migration = migration.replace(" DEFAULT NOW()", "")
        async with pool.acquire() as connection:
            await connection.execute(
                "CREATE TEMP TABLE resources_ward (id BIGINT PRIMARY KEY);"
                "INSERT INTO resources_ward VALUES (101), (102);"
            )
            await connection.execute(
                migration.replace("CREATE TABLE", "CREATE TEMP TABLE").replace(
                    "archive.", ""
                )
            )
        monkeypatch.setattr(
            report_store,
            "_UPSERT_REPORT_SQL",
            report_store._UPSERT_REPORT_SQL.replace("archive.", "pg_temp."),
        )
        store = report_store.AsyncpgWeeklyReportStore(
            report_store.WeeklyReportStorageSettings(dsn=dsn, batch_size=1)
        )
        store._pool = pool
        original = report_store.WeeklyReportStorageRecord(
            ward_id=101,
            week_start_date=date(2026, 8, 3),
            week_end_date=date(2026, 8, 9),
            weekly_score=93,
            weekly_status="GOOD",
            report_data_json='{"summary":"original"}',
        )

        async def save(*records):
            async def stream():
                for record in records:
                    yield record

            return await store.upsert_reports(stream())

        assert await save(original) == 1
        async with pool.acquire() as connection:
            before = await connection.fetchrow(
                "SELECT * FROM pg_temp.resources_ward_weekly_report"
            )
        updated = replace(
            original,
            weekly_score=70,
            weekly_status="CAUTION",
            report_data_json='{"summary":"updated"}',
        )
        assert await save(updated, updated) == 2
        # Concurrent callers share the bounded pool, as in a worker process.
        assert await asyncio.gather(save(updated), save(updated)) == [1, 1]
        assert (
            await save(
                replace(original, ward_id=102),
                replace(
                    original,
                    week_start_date=date(2026, 8, 10),
                    week_end_date=date(2026, 8, 16),
                ),
            )
            == 2
        )
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT * FROM pg_temp.resources_ward_weekly_report "
                "ORDER BY ward_id, week_start_date"
            )
        assert len(rows) == 3
        after = rows[0]
        assert before["created_at"] is not None
        assert before["updated_at"] is not None
        assert after["id"] == before["id"]
        assert after["created_at"] == before["created_at"]
        assert after["updated_at"] > before["updated_at"]
        assert after["weekly_score"] == 70
        assert after["weekly_status"] == "CAUTION"
        assert json.loads(after["report_data"]) == {"summary": "updated"}


@pytest.mark.asyncio
async def test_not_null_recovery_uses_real_savepoints(monkeypatch):
    dsn = os.environ.get("WEEKLY_REPORT_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("WEEKLY_REPORT_TEST_DATABASE_DSN is required")
    async with asyncpg.create_pool(dsn, min_size=1, max_size=1) as pool:
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TEMP TABLE resources_ward_weekly_report (
                    ward_id bigint NOT NULL,
                    week_start_date date NOT NULL,
                    week_end_date date NOT NULL,
                    weekly_score smallint NOT NULL,
                    weekly_status text,
                    report_data jsonb NOT NULL,
                    created_at timestamptz NOT NULL,
                    updated_at timestamptz NOT NULL,
                    UNIQUE (ward_id, week_start_date)
                )
            """)
        monkeypatch.setattr(
            report_store,
            "_UPSERT_REPORT_SQL",
            report_store._UPSERT_REPORT_SQL.replace("archive.", "pg_temp."),
        )
        store = report_store.AsyncpgWeeklyReportStore(
            report_store.WeeklyReportStorageSettings(dsn=dsn, batch_size=3)
        )
        store._pool = pool

        async def records():
            for ward in range(1, 5):
                yield report_store.WeeklyReportStorageRecord(
                    ward,
                    date(2026, 8, 31),
                    date(2026, 9, 6),
                    None if ward == 2 else 90,
                    "GOOD",
                    "{}",
                )

        for _ in range(2):
            outcome = await store.upsert_reports_skipping_not_null(records())
            assert outcome.written_count == 3
            assert outcome.skipped == (
                report_store.WeeklyReportStorageRejection(2, "weekly_score"),
            )
        async with pool.acquire() as conn:
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM pg_temp.resources_ward_weekly_report"
                )
                == 3
            )
