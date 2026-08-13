from datetime import date

import pytest
from ax_contracts import UserWeeklyMetrics

from workflows.weekly_report.models import DailyActivity, UserActivityWindow
from workflows.weekly_report.nodes import calculate_metrics
from workflows.weekly_report.rendering import (
    build_fallback_narrative,
    render_report,
)
from workflows.weekly_report.repository import MockWeeklyActivityRepository


@pytest.mark.asyncio
async def test_calculates_known_mock_user_metrics() -> None:
    repository = MockWeeklyActivityRepository()
    users = await repository.load_activity(
        week_start=date(2026, 8, 3),
        timezone="Asia/Seoul",
    )

    result = await calculate_metrics(
        {
            "week_start": "2026-08-03",
            "week_end": "2026-08-10",
            "timezone": "Asia/Seoul",
            "work_item": users[0].model_dump(mode="json"),
        }
    )
    metrics = result["metrics"]

    assert metrics["current"] == {
        "schema_version": "1",
        "assigned_tasks": 10,
        "completed_tasks": 9,
        "completion_rate_percent": 90.0,
        "focus_minutes": 1500,
        "active_days": 5,
        "blockers_opened": 1,
        "blockers_resolved": 1,
    }
    assert metrics["previous"]["completion_rate_percent"] == 60.0
    assert metrics["delta"]["completion_rate_percentage_points"] == 30.0
    assert metrics["delta"]["focus_minutes"] == 300


@pytest.mark.asyncio
async def test_inactive_user_has_zero_metrics_without_division_error() -> None:
    user = UserActivityWindow(
        user_id="inactive",
        display_name="휴식 사용자",
        records=[
            DailyActivity(
                activity_date=date(2026, 8, 3),
                assigned_tasks=0,
                completed_tasks=0,
                focus_minutes=0,
                blockers_opened=0,
                blockers_resolved=0,
            )
        ],
    )
    result = await calculate_metrics(
        {
            "week_start": "2026-08-03",
            "week_end": "2026-08-10",
            "timezone": "Asia/Seoul",
            "work_item": user.model_dump(mode="json"),
        }
    )

    assert result["metrics"]["current"]["completion_rate_percent"] == 0.0
    assert result["metrics"]["current"]["active_days"] == 0


@pytest.mark.asyncio
async def test_fallback_report_is_complete_and_disclosed() -> None:
    users = await MockWeeklyActivityRepository().load_activity(
        week_start=date(2026, 8, 3),
        timezone="Asia/Seoul",
    )
    calculated = await calculate_metrics(
        {
            "week_start": "2026-08-03",
            "week_end": "2026-08-10",
            "timezone": "Asia/Seoul",
            "work_item": users[1].model_dump(mode="json"),
        }
    )
    metrics = UserWeeklyMetrics.model_validate(calculated["metrics"])

    report = render_report(
        metrics,
        build_fallback_narrative(metrics),
        "template_fallback",
    )

    assert "## 핵심 지표" in report.markdown
    assert "## 이번 주 요약" in report.markdown
    assert "## 다음 주 제안" in report.markdown
    assert "자동 대체됨" in report.markdown
    assert report.generation_mode == "template_fallback"
