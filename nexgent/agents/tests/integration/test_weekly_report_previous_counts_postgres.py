"""Read-only SQL test with inline fixtures; no database objects or rows are changed."""

import json
import os
from datetime import date

import asyncpg
import pytest

from workflows.weekly_report.source.queries import PREVIOUS_ACTIVITY_COUNTS_SQL
from workflows.weekly_report.source.service import _saved_count


@pytest.mark.asyncio
async def test_saved_counts_query_selects_only_exact_prior_week_and_requested_wards():
    dsn = os.environ.get("WEEKLY_REPORT_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("WEEKLY_REPORT_TEST_DATABASE_DSN is required")

    def report(motion, remote):
        return {
            "living_activity": {
                "activity_detection": {
                    "metrics": {"current_week": motion, "previous_week": 99999}
                },
                "remote_control_usage": {
                    "metrics": {"current_week": remote, "previous_week": 88888}
                },
            }
        }

    fixtures = [
        {
            "ward_id": ward,
            "week_start_date": start,
            "week_end_date": end,
            "report_data": data,
        }
        for ward, start, end, data in [
            (10, "2026-10-19", "2026-10-25", report(2278, 1123)),
            (10, "2026-10-12", "2026-10-18", report(2989, 2490)),
            (10, "2026-10-26", "2026-11-01", report(2710, 1967)),
            (20, "2026-10-19", "2026-10-25", report(None, 0)),
            (30, "2026-10-19", "2026-10-24", report(100, 200)),
            (40, "2026-10-19", "2026-10-25", report(999, 999)),
            (50, "2026-10-19", "2026-10-25", report("123", True)),
            (60, "2026-10-19", "2026-10-25", {}),
        ]
    ]
    fixture_cte = """
        WITH saved_reports AS (
            SELECT * FROM jsonb_to_recordset($4::jsonb) AS r(
                ward_id bigint, week_start_date date, week_end_date date,
                report_data jsonb
            )
        )
    """
    connection = await asyncpg.connect(
        dsn,
        timeout=10,
        server_settings={
            "default_transaction_read_only": "on",
            "statement_timeout": "10000",
        },
    )
    try:
        async with connection.transaction(readonly=True):
            rows = await connection.fetch(
                fixture_cte
                + PREVIOUS_ACTIVITY_COUNTS_SQL.replace(
                    "archive.resources_ward_weekly_report",
                    "saved_reports",
                ),
                [10, 20, 30, 50, 60],
                date(2026, 10, 19),
                date(2026, 10, 25),
                json.dumps(fixtures),
            )
        assert [row["ward_id"] for row in rows] == [10, 20, 50, 60]
        assert [
            (
                _saved_count(row["movement_count_total"]),
                _saved_count(row["remote_control_count_total"]),
            )
            for row in rows
        ] == [
            (2278, 1123),
            (None, 0),
            (None, None),
            (None, None),
        ]
    finally:
        await connection.close()
