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
    assert "- 가입자 상태 점수: 86점" in report.markdown
    assert "- 상태 안내: 이번 주 가입자 상태 점수는 양호 범위였어요." in report.markdown
    assert "점수 범위:" not in report.markdown
    assert "## 한주 총평" in report.markdown
    assert "이번 주에는 최근 안부를 편안하게 확인해 보셔도 좋아요." in report.markdown
    assert "## 1. 수면 패턴" in report.markdown
    assert "  - 이번 주: 오후 10:40" in report.markdown
    assert "## 4. 기기 데이터 수신" in report.markdown
    assert "### 위험 관리 기록" in report.markdown
    assert "상세 기록은 현재 주간 리포트 데이터에 포함되지 않아요." in report.markdown
    assert "# 보호자 행동 제안" in report.markdown
    assert "- 근거: 생활 흐름에 일부 변화가 보였어요." in report.markdown
    assert "- 권장 행동: 최근 안부를 편안하게 확인해 보셔도 좋아요." in report.markdown


@pytest.mark.asyncio
async def test_report_omits_sleep_section_when_current_sleep_data_is_absent() -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    metrics = metrics.model_copy(
        update={
            "current": metrics.current.model_copy(
                update={
                    "sleep_time_avg": None,
                    "wake_up_time_avg": None,
                    "night_awake_count_avg": None,
                }
            ),
            "delta": metrics.delta.model_copy(
                update={
                    "sleep_time_minutes": None,
                    "wake_up_time_minutes": None,
                    "night_awake_count_avg": None,
                }
            ),
        }
    )
    narrative = WeeklyNarrative(
        headline="이번 주 생활 흐름을 살펴봤어요.",
        analysis_text=(
            "이번 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료를 지난주와 함께 살펴봤어요. "
            "측정된 변화만으로 이유를 단정하지 않았어요. "
            "평소 모습과 함께 편안하게 살펴보셔도 좋아요."
        ),
        observations=["생활 흐름을 확인했어요."],
        suggestions=["최근 안부를 편안하게 확인해 보셔도 좋아요."],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert "수면 패턴" not in report.markdown
    assert "평균 취침 시간" not in report.markdown
    assert "## 1. 활동량" in report.markdown
    assert "## 2. 실내 환경" in report.markdown
    assert "## 3. 기기 데이터 수신" in report.markdown
    assert "## 4. 위험 관리" in report.markdown


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

    assert "- 상태: 양호" in report.markdown
    assert "이번 주 최고 온도와 최고 습도는 생활하기 좋은 범위에 있었어요." in report.markdown
    assert "- 적정 범위: 26~28℃" in report.markdown
    assert "- 적정 범위: 40~60%" in report.markdown


@pytest.mark.parametrize(
    ("temperature_max", "humidity_max", "status", "feedback"),
    [
        (
            28,
            60,
            "양호",
            "이번 주 최고 온도와 최고 습도는 생활하기 좋은 범위에 있었어요.",
        ),
        (
            29,
            60,
            "주의",
            "이번 주 최고 온도가 권장 범위보다 높아 생활하기 불편할 수 있어요.",
        ),
        (
            28,
            65,
            "주의",
            "이번 주 최고 습도가 적정 범위를 벗어나 주의가 필요해요.",
        ),
        (
            31,
            60,
            "위험",
            "이번 주 최고 온도가 권장 범위보다 크게 높아 냉난방 상태 확인이 필요해요.",
        ),
        (
            28,
            71,
            "위험",
            "이번 주 최고 습도가 크게 벗어나 습한 실내 환경이 확인됐어요.",
        ),
        (
            31,
            71,
            "위험",
            "이번 주 최고 온도와 최고 습도가 크게 벗어나 냉난방·환기 상태 확인이 필요해요.",
        ),
    ],
)
@pytest.mark.asyncio
async def test_report_gives_effective_feedback_from_weekly_environment_maxima(
    temperature_max: float,
    humidity_max: float,
    status: str,
    feedback: str,
) -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0].model_copy(
        update={
            "current": source.items[0].current.model_copy(
                update={
                    "temperature_max": temperature_max,
                    "humidity_max": humidity_max,
                }
            )
        }
    )
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
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert f"- 상태: {status}" in report.markdown
    assert feedback in report.markdown
    assert "반복" not in report.markdown


@pytest.mark.parametrize(
    ("average", "score", "description"),
    [
        (0.0, "0점", "위험 범위였어요."),
        (25.49, "25점", "위험 범위였어요."),
        (25.5, "26점", "주의 범위였어요."),
        (75.49, "75점", "주의 범위였어요."),
        (75.5, "76점", "양호 범위였어요."),
        (100.0, "100점", "양호 범위였어요."),
    ],
)
@pytest.mark.asyncio
async def test_report_classifies_rounded_weekly_average_risk_score(
    average: float,
    score: str,
    description: str,
) -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    current = metrics.current.model_copy(update={"risk_score_avg": average})
    previous = metrics.previous
    metrics = metrics.model_copy(
        update={
            "current": current,
            "delta": metrics.delta.model_copy(
                update={"risk_score_avg": average - previous.risk_score_avg}
            ),
        }
    )
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
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert f"- 가입자 상태 점수: {score}" in report.markdown
    assert description in report.markdown


@pytest.mark.asyncio
async def test_report_discloses_missing_weekly_average_risk_score() -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    metrics = metrics.model_copy(
        update={
            "current": metrics.current.model_copy(update={"risk_score_avg": None}),
            "delta": metrics.delta.model_copy(update={"risk_score_avg": None}),
        }
    )
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
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert "- 가입자 상태 점수: 자료 없음" in report.markdown
    assert "이번 주 가입자 상태 점수를 계산할 자료가 없어요." in report.markdown
