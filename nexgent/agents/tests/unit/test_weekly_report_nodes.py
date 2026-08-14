from datetime import date

import pytest
from ax_contracts import WardWeeklyMetrics

from workflows.weekly_report.nodes import calculate_metrics
from workflows.weekly_report.rendering import (
    build_fallback_narrative,
    render_report,
)
from workflows.weekly_report.repository import MockWeeklyWardRiskRepository


@pytest.mark.asyncio
async def test_calculates_known_mock_ward_metrics() -> None:
    selection = await MockWeeklyWardRiskRepository().load_week(
        week_start=date(2026, 8, 3), timezone="Asia/Seoul"
    )

    result = await calculate_metrics(
        {
            "week_start": "2026-08-03",
            "week_end": "2026-08-10",
            "timezone": "Asia/Seoul",
            "work_item": selection.windows[0].model_dump(mode="json"),
        }
    )

    assert result["metrics"]["current"]["danger_days"] == 2
    assert result["metrics"]["previous"]["danger_days"] == 1
    assert result["metrics"]["delta"]["danger_days"] == 1


@pytest.mark.asyncio
async def test_fallback_report_is_grounded_complete_and_disclosed() -> None:
    selection = await MockWeeklyWardRiskRepository().load_week(
        week_start=date(2026, 8, 3), timezone="Asia/Seoul"
    )
    calculated = await calculate_metrics(
        {
            "week_start": "2026-08-03",
            "week_end": "2026-08-10",
            "timezone": "Asia/Seoul",
            "work_item": selection.windows[1].model_dump(mode="json"),
        }
    )
    metrics = WardWeeklyMetrics.model_validate(calculated["metrics"])

    report = render_report(
        metrics, build_fallback_narrative(metrics), "template_fallback"
    )

    assert "| 위험 감지일 | 1일 | 2일 | -1일 |" in report.markdown
    assert "## 이번 주 요약" in report.markdown
    assert "## 다음 주 제안" in report.markdown
    assert "자동 대체됨" in report.markdown
