import sqlite3
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from ax_contracts import WeeklyReportRequest

from workflows.weekly_report.source.queries import (
    CANDIDATE_WARDS_SQL,
    DAILY_ROWS_SQL,
    DISPATCH_AGGREGATES_SQL,
    EXPLICIT_WARDS_SQL,
    RISK_AGGREGATES_SQL,
)
from workflows.weekly_report.source.service import (
    SourceRequestError,
    WeeklyReportSourceService,
)


class FakeDatabase:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def start(self) -> None: pass

    async def close(self) -> None: pass

    async def health(self) -> bool: return True

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        return {"ok": 1}

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        self.calls.append((query, args))
        if query == CANDIDATE_WARDS_SQL:
            return [
                {"ward_id": 10, "full_name": "첫 대상"},
                {"ward_id": 20, "full_name": "둘째 대상"},
                {"ward_id": 30, "full_name": "셋째 대상"},
            ]
        if query == DAILY_ROWS_SQL:
            return []
        if query == RISK_AGGREGATES_SQL:
            return [
                {
                    "ward_id": ward_id,
                    "period_index": index,
                    "risk_detected_count": 0,
                    "risk_resolved_count": 0,
                    "risk_score_avg": None,
                    "danger_days": 0,
                }
                for ward_id in args[0]
                for index in (0, 1)
            ]
        if query == DISPATCH_AGGREGATES_SQL:
            return []
        return []


@pytest.mark.asyncio
async def test_source_service_pages_candidates_with_opaque_cursor() -> None:
    service = WeeklyReportSourceService(FakeDatabase())
    request = WeeklyReportRequest(week_start=date(2026, 8, 3), limit=2)
    result = await service.build(request)
    assert [item.ward_id for item in result.items] == [10, 20]
    assert result.next_cursor

    next_request = WeeklyReportRequest(
        week_start=date(2026, 8, 3), limit=2, cursor=result.next_cursor
    )
    assert service._decode_cursor(next_request) == 20


def test_cursor_is_bound_to_period_and_timezone() -> None:
    service = WeeklyReportSourceService(FakeDatabase())
    first = WeeklyReportRequest(week_start=date(2026, 8, 3))
    cursor = service._encode_cursor(first, 20)
    changed = WeeklyReportRequest(
        week_start=date(2026, 8, 10), cursor=cursor, timezone="Asia/Seoul"
    )
    with pytest.raises(SourceRequestError, match="does not match"):
        service._decode_cursor(changed)


def test_source_period_timestamps_are_timezone_aware() -> None:
    value = datetime.combine(date(2026, 8, 3), datetime.min.time(), ZoneInfo("Asia/Seoul"))
    assert value.utcoffset() is not None


@pytest.mark.parametrize(
    ("query", "table"),
    [
        (CANDIDATE_WARDS_SQL, "resources_ward"),
        (EXPLICIT_WARDS_SQL, "resources_ward"),
        (DAILY_ROWS_SQL, "analysis_devicedailysummary"),
        (RISK_AGGREGATES_SQL, "analysis_wardevaluation"),
        (DISPATCH_AGGREGATES_SQL, "dispatch_dispatchrequest"),
    ],
)
def test_source_queries_are_bound_to_authoritative_ansimk_schema(query, table) -> None:
    assert f"ansimk.{table}" in query
    assert "ansimk_clone." not in query
    assert "archive." not in query


def roster_connection():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("ATTACH DATABASE ':memory:' AS ansimk")
    connection.executescript("""
        CREATE TABLE ansimk.resources_ward (id INTEGER, full_name TEXT);
        CREATE TABLE ansimk.resources_location (id INTEGER, ward_id INTEGER);
        CREATE TABLE ansimk.resources_device
            (id INTEGER, location_id INTEGER, is_disconnected BOOLEAN);
        INSERT INTO ansimk.resources_ward VALUES
            (5, 'no location'), (10, 'first'), (15, 'empty location'),
            (20, 'second'), (30, NULL), (40, 'no device');
        INSERT INTO ansimk.resources_location VALUES
            (100, 10), (101, 10), (150, 15), (200, 20), (300, 30), (400, 40);
        INSERT INTO ansimk.resources_device VALUES
            (1, 100, FALSE), (2, 100, FALSE), (3, 101, TRUE),
            (4, 200, FALSE), (5, 300, TRUE), (6, NULL, FALSE);
    """)
    return connection


@pytest.mark.asyncio
async def test_discovery_skips_no_device_wards_and_keeps_eligible_no_data_wards() -> None:
    class RosterDatabase(FakeDatabase):
        async def fetch(self, query, *args):
            if query == CANDIDATE_WARDS_SQL:
                with roster_connection() as connection:
                    return [dict(row) for row in connection.execute(
                        query, {"1": args[0], "2": args[1]}
                    )]
            return []

    service = WeeklyReportSourceService(RosterDatabase())
    request = WeeklyReportRequest(week_start=date(2026, 9, 14), limit=2)
    first = await service.build(request)
    second = await service.build(request.model_copy(update={"cursor": first.next_cursor}))

    items = first.items + second.items
    assert [item.ward_id for item in items] == [10, 20, 30]
    assert second.next_cursor is None
    assert all(item.current.covered_days == 0 for item in items)
    assert all(item.current.risk_score_avg is None for item in items)
    assert all(item.current.movement_count_total is None for item in items)


@pytest.mark.asyncio
@pytest.mark.parametrize("only_no_device", [False, True])
async def test_explicit_selection_skips_no_device_before_loading_metrics(only_no_device):
    class ExplicitDatabase(FakeDatabase):
        async def fetch(self, query, *args):
            if query == EXPLICIT_WARDS_SQL:
                placeholders = ", ".join("?" for _ in args[0])
                query = query.replace("= ANY($1::bigint[])", f"IN ({placeholders})")
                with roster_connection() as connection:
                    rows = [dict(row) for row in connection.execute(query, args[0])]
                for row in rows:
                    row["has_device"] = bool(row["has_device"])
                return rows
            return await super().fetch(query, *args)

    database = ExplicitDatabase()
    requested = [15] if only_no_device else [10, 15, 99]
    result = await WeeklyReportSourceService(database).build(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=requested)
    )
    assert [item.ward_id for item in result.items] == ([] if only_no_device else [10])
    assert {(item.ward_id, item.reason) for item in result.skipped} == (
        {(15, "no_device")} if only_no_device
        else {(15, "no_device"), (99, "not_found")}
    )
    assert all(args[0] == [10] for _, args in database.calls)
    if only_no_device:
        assert database.calls == []
