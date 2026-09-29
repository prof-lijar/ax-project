"""Read-only SQL fixtures; no table creation or application data access."""

import os
from datetime import date

import asyncpg
import pytest

from workflows.weekly_report import completion_notification as coverage


@pytest.mark.asyncio
async def test_production_coverage_sql_with_postgres_fixtures(monkeypatch):
    dsn = os.environ.get("WEEKLY_REPORT_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("WEEKLY_REPORT_TEST_DATABASE_DSN is required")
    query = (
        coverage.COVERAGE_SQL.replace(
            "ansimk.resources_ward_weekly_report", "fixture_reports"
        )
        .replace("ansimk.resources_ward", "fixture_wards")
        .replace(
            "WITH wards AS",
            """WITH fixture_wards(id, address) AS (VALUES
        (1, '경상북도 울진군 북면'), (2, '경북 영덕군 영덕읍'),
        (3, '경기도 광명시 철산동'), (4, '서울특별시 광명로 1'),
        (5, NULL), (6, ''), (7, '울진'), (8, '영덕군'), (9, '광명시')
    ), fixture_reports(ward_id, week_start_date) AS (VALUES
        (1, DATE '2026-09-21'), (1, DATE '2026-09-21'),
        (2, DATE '2026-09-21'), (3, DATE '2026-09-21'),
        (4, DATE '2026-09-21'), (999, DATE '2026-09-21'),
        (1, DATE '2026-09-14'), (3, DATE '2026-09-14'),
        (2, DATE '2026-09-07')
    ), wards AS""",
        )
    )
    monkeypatch.setattr(coverage, "COVERAGE_SQL", query)
    connection = await asyncpg.connect(dsn, timeout=10)
    try:
        result = await coverage.collect_coverage(connection, date(2026, 9, 21))
    finally:
        await connection.close()
    current, previous = [week["regions"] for week in result["weeks"]]
    assert current["전체"] == {"total": 9, "success": 4}
    assert previous["전체"] == {"total": 9, "success": 2}
    for region in ("울진", "영덕", "광명"):
        assert current[region] == {"total": 2, "success": 1}
    assert current["기타"] == {"total": 3, "success": 1}
    assert previous["영덕"] == {"total": 2, "success": 0}
