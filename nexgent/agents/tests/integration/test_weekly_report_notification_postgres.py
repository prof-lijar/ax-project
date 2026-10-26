"""Read-only SQL fixtures; no table creation or application data access."""

import os
from datetime import date

import asyncpg
import pytest

from workflows.weekly_report import completion_notification as coverage


@pytest.mark.asyncio
async def test_local_coverage_sql_with_postgres_fixtures(monkeypatch):
    dsn = os.environ.get("WEEKLY_REPORT_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("WEEKLY_REPORT_TEST_DATABASE_DSN is required")
    query = (
        coverage.COVERAGE_SQL.replace(
            "archive.resources_ward_weekly_report", "fixture_reports"
        )
        .replace("ansimk.resources_ward", "fixture_wards")
        .replace("ansimk.resources_location", "fixture_locations")
        .replace("ansimk.resources_device", "fixture_devices")
        .replace(
            "WITH wards AS",
            """WITH fixture_wards(id, address) AS (VALUES
        (1, '경상북도 울진군 북면'), (2, '경북 영덕군 영덕읍'),
        (3, '경기도 광명시 철산동'), (4, '서울특별시 광명로 1'),
        (5, NULL), (6, ''), (7, '울진'),
        (8, '영덕군'), (9, '광명시'), (10, '울진'), (11, '영덕군')
    ), fixture_locations(id, ward_id) AS (VALUES
        (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7),
        (8, 8), (9, 9), (10, 10), (12, 1)
    ), fixture_devices(id, location_id) AS (VALUES
        (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7),
        (8, 8), (9, 9), (12, 12), (13, 1), (14, NULL)
    ), fixture_reports(ward_id, week_start_date) AS (VALUES
        (1, DATE '2026-09-21'), (1, DATE '2026-09-21'),
        (2, DATE '2026-09-21'), (3, DATE '2026-09-21'),
        (4, DATE '2026-09-21'), (999, DATE '2026-09-21'),
        (10, DATE '2026-09-21'),
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
    assert current["전체"] == {"total": 9, "success": 4, "skipped": 2}
    assert previous["전체"] == {"total": 9, "success": 2, "skipped": 2}
    for region in ("울진", "영덕", "광명"):
        assert current[region] == {"total": 2, "success": 1, "skipped": int(region != "광명")}
    assert current["기타"] == {"total": 3, "success": 1, "skipped": 0}
    assert previous["영덕"] == {"total": 2, "success": 0, "skipped": 1}
