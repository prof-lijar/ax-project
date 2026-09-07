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


def test_source_queries_are_bound_to_authoritative_ansimk_schema() -> None:
    combined = (
        f"{CANDIDATE_WARDS_SQL}\n{EXPLICIT_WARDS_SQL}\n{DAILY_ROWS_SQL}\n"
        f"{RISK_AGGREGATES_SQL}\n{DISPATCH_AGGREGATES_SQL}"
    )
    for table in (
        "resources_ward",
        "analysis_devicedailysummary",
        "analysis_wardevaluation",
        "dispatch_dispatchrequest",
    ):
        assert f"ansimk.{table}" in combined
    assert "ansimk_clone." not in combined
    assert "archive." not in combined
