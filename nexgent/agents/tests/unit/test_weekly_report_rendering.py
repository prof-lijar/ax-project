from datetime import date

import pytest
from ax_contracts import (
    NarrativeGenerationMetadata,
    WeeklyNarrative,
    WeeklyReportRequest,
)

from workflows.weekly_report.domain.rendering import render_report
from workflows.weekly_report.tools.source_repository import (
    MockWeeklyReportSourceRepository,
)


@pytest.mark.asyncio
async def test_report_uses_guardian_facing_section_template() -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    narrative = WeeklyNarrative(
        headline="이번 주 생활 흐름을 차분히 살펴봤어요.",
        analysis_text=(
            "이번 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료에서는 지난주와 다른 부분도 있었지만 이유를 단정하지 않았어요. "
            "활동과 휴식 흐름은 평소 모습과 함께 살펴보면 좋아요. "
            "자료가 충분한 부분만 나란히 비교했어요."
        ),
        observations=["생활 흐름에 일부 변화가 보였어요."],
        suggestions=["최근 안부를 편안하게 확인해 보셔도 좋아요."],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(
            prompt_version="test",
            validation_status="passed",
        ),
    )

    assert report.markdown.startswith("# 주간 생활 리포트")
    assert "- 가입자: 관리 대상 101" in report.markdown
    assert "- 주차: 8월 1주차" in report.markdown
    assert "- 기간: 2026-08-03(월) ~ 2026-08-09(일)" in report.markdown
    assert "- 가입자 상태 점수: 산정 기준 없음" in report.markdown
    assert "## 1. 수면 패턴" in report.markdown
    assert "  - 이번 주: 오후 10:40" in report.markdown
    assert "## 4. 기기 데이터 수신" in report.markdown
    assert "### 위험 관리 기록" in report.markdown
    assert "상세 기록은 현재 주간 리포트 데이터에 포함되지 않아요." in report.markdown
    assert "# 보호자 행동 제안" in report.markdown
    assert "- 근거: 생활 흐름에 일부 변화가 보였어요." in report.markdown
    assert "- 권장 행동: 최근 안부를 편안하게 확인해 보셔도 좋아요." in report.markdown


@pytest.mark.asyncio
async def test_report_renders_approved_monthly_environment_ranges() -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    narrative = WeeklyNarrative(
        headline="이번 주 생활 흐름을 살펴봤어요.",
        analysis_text=(
            "이번 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료를 지난주와 함께 살펴봤어요. "
            "측정된 변화만으로 이유를 단정하지 않았어요. "
            "평소 모습과 함께 편안하게 살펴보셔도 좋아요."
        ),
        observations=["생활 흐름을 확인했어요."],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(
            prompt_version="test",
            validation_status="passed",
        ),
    )

    assert "- 상태 범위: 판정 기준 없음" in report.markdown
    assert "- 상태: 온도 낮음 · 습도 적정" in report.markdown
    assert "- 적정 범위: 26~28℃" in report.markdown
    assert "- 적정 범위: 40~60%" in report.markdown
    assert "86점" not in report.markdown
