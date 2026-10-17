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


@pytest.mark.asyncio
async def test_discovery_includes_every_ward_without_any_weekly_records() -> None:
    class RosterDatabase(FakeDatabase):
        async def fetch(self, query, *args):
            if query == CANDIDATE_WARDS_SQL:
                with sqlite3.connect(":memory:") as connection:
                    connection.execute("ATTACH DATABASE ':memory:' AS archive")
                    connection.execute("ATTACH DATABASE ':memory:' AS ansimk")
                    connection.execute(
                        "CREATE TABLE archive.resources_ward (id INTEGER, full_name TEXT)"
                    )
                    connection.execute(
                        "INSERT INTO archive.resources_ward VALUES (99, 'other schema')"
                    )
                    connection.execute(
                        "CREATE TABLE ansimk.resources_ward (id INTEGER, full_name TEXT)"
                    )
                    connection.executemany(
                        "INSERT INTO ansimk.resources_ward VALUES (?, ?)",
                        [(10, "첫 대상"), (20, "둘째 대상"), (30, None)],
                    )
                    return [dict(zip(("ward_id", "full_name"), row, strict=True))
                            for row in connection.execute(query, {"1": args[0], "2": args[1]})]
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
