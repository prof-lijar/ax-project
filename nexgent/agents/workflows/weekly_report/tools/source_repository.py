"""Weekly-report source port, HTTP implementation, and deterministic fixture."""

from __future__ import annotations

from datetime import time
from functools import lru_cache
from typing import Protocol

from ax_contracts import (
    WardWeeklyMetricDelta,
    WardWeeklyMetrics,
    WardWeeklyMetricSnapshot,
    WeeklyReportRequest,
    WeeklyReportSourceResponse,
)

from .source_api_client import SourceApiSettings, WeeklyReportSourceApiClient


class WeeklyReportSourceRepository(Protocol):
    async def load(self, request: WeeklyReportRequest) -> WeeklyReportSourceResponse: ...


class HttpWeeklyReportSourceRepository:
    def __init__(self, client: WeeklyReportSourceApiClient | None = None) -> None:
        self.client = client or WeeklyReportSourceApiClient(SourceApiSettings.from_env())

    async def load(self, request: WeeklyReportRequest) -> WeeklyReportSourceResponse:
        return await self.client.load(request)


class MockWeeklyReportSourceRepository:
    """Three varied wards with complete current and previous metadata."""

    async def load(self, request: WeeklyReportRequest) -> WeeklyReportSourceResponse:
        ward_ids = request.ward_ids or [101, 102, 103]
        items = []
        for ward_id in ward_ids[: request.limit]:
            previous = _snapshot(ward_id, current=False)
            current = _snapshot(ward_id, current=True)
            items.append(
                WardWeeklyMetrics(
                    ward_id=ward_id,
                    display_name=f"관리 대상 {ward_id}",
                    week_start=request.week_start,
                    week_end=request.week_end,
                    current=current,
                    previous=previous,
                    delta=_mock_delta(current, previous),
                )
            )
        return WeeklyReportSourceResponse(
            week_start=request.week_start,
            week_end=request.week_end,
            timezone=request.timezone,
            items=items,
        )


def _snapshot(ward_id: int, *, current: bool) -> WardWeeklyMetricSnapshot:
    shift = (ward_id % 3) - 1
    danger_days = max(0, 1 + (shift if current else 0))
    return WardWeeklyMetricSnapshot(
        covered_days=7,
        daily_summary_count=7,
        device_count=1,
        temperature_avg=23.0 + (0.5 if current else 0),
        temperature_min=20.0,
        temperature_max=26.0,
        temperature_count=84,
        humidity_avg=48.0 + (2 if current else 0),
        humidity_min=40.0,
        humidity_max=58.0,
        humidity_count=84,
        light_avg=110.0,
        light_min=5.0,
        light_max=500.0,
        light_count=84,
        light_on_time_minutes_avg=360.0 + (15 if current else 0),
        movement_count_avg=24.0 + (shift * 3 if current else 0),
        remote_control_count_avg=5.0,
        wake_up_time_avg=time(7, 20),
        sleep_time_avg=time(22, 40),
        night_awake_count_avg=1.0,
        risk_detected_count=danger_days,
        risk_resolved_count=1 if danger_days else 0,
        risk_score_avg=80.0 + (6.0 * shift if current else 0),
        danger_days=danger_days,
        dispatch_request_count=1 if ward_id == 103 and current else 0,
        unresolved_dispatch_count=1 if ward_id == 103 and current else 0,
    )


def _mock_delta(
    current: WardWeeklyMetricSnapshot, previous: WardWeeklyMetricSnapshot
) -> WardWeeklyMetricDelta:
    def difference(left: float | None, right: float | None) -> float | None:
        return left - right if left is not None and right is not None else None

    return WardWeeklyMetricDelta(
        covered_days=current.covered_days - previous.covered_days,
        temperature_avg=difference(current.temperature_avg, previous.temperature_avg),
        humidity_avg=difference(current.humidity_avg, previous.humidity_avg),
        light_avg=difference(current.light_avg, previous.light_avg),
        light_on_time_minutes_avg=difference(
            current.light_on_time_minutes_avg, previous.light_on_time_minutes_avg
        ),
        movement_count_avg=difference(
            current.movement_count_avg, previous.movement_count_avg
        ),
        remote_control_count_avg=difference(
            current.remote_control_count_avg, previous.remote_control_count_avg
        ),
        wake_up_time_minutes=0,
        sleep_time_minutes=0,
        night_awake_count_avg=difference(
            current.night_awake_count_avg, previous.night_awake_count_avg
        ),
        risk_detected_count=current.risk_detected_count - previous.risk_detected_count,
        risk_resolved_count=current.risk_resolved_count - previous.risk_resolved_count,
        risk_score_avg=difference(current.risk_score_avg, previous.risk_score_avg),
        danger_days=current.danger_days - previous.danger_days,
        dispatch_request_count=(
            current.dispatch_request_count - previous.dispatch_request_count
        ),
        unresolved_dispatch_count=(
            current.unresolved_dispatch_count - previous.unresolved_dispatch_count
        ),
    )


@lru_cache(maxsize=1)
def get_weekly_report_source_repository() -> WeeklyReportSourceRepository:
    return HttpWeeklyReportSourceRepository()
