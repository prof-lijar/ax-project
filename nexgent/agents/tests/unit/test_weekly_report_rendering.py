from datetime import date

import pytest
from ax_contracts import (
    NarrativeGenerationMetadata,
    WeeklyNarrative,
    WeeklyReportRequest,
)

from workflows.weekly_report.domain.rendering import render_report
from workflows.weekly_report.domain.risk_score_policy import (
    assess_risk_score,
    risk_score_description,
)
from workflows.weekly_report.tools.source_repository import (
    MockWeeklyReportSourceRepository,
)


def test_risk_score_description_uses_approved_good_copy() -> None:
    description = risk_score_description(assess_risk_score(86))

    assert description == "지난 한 주는 대체로 안정적인 상태가 유지됐어요."


@pytest.mark.asyncio
async def test_report_uses_guardian_facing_section_template() -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0].model_copy(update={"display_name": "주필기"})
    narrative = WeeklyNarrative(
        headline="지난 한 주 생활 흐름을 차분히 살펴봤어요.",
        analysis_text=(
            "지난 한 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료에서는 2주 전과 다른 부분도 있었지만 이유를 단정하지 않았어요. "
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
    assert "- 가입자: 주필기" in report.markdown
    assert "- 주차: 8월 1주차" in report.markdown
    assert "- 기간: 2026-08-03(월) ~ 2026-08-09(일)" in report.markdown
    assert "- 가입자 상태 점수: 86점" in report.markdown
    assert "- 상태: GOOD" in report.markdown
    assert (
        "- 상태 안내: 지난 한 주는 대체로 안정적인 상태가 유지됐어요."
        in report.markdown
    )
    assert (
        "지난 한 주 주필기님은 대체로 안정적인 생활 흐름을 유지하셨습니다."
        in report.markdown
    )
    assert "점수 범위:" not in report.markdown
    assert "## 한주 총평" in report.markdown
    assert (
        "이번 주에는 평소처럼 안부를 확인하며 현재의 생활 흐름을 유지해 주세요."
        in report.markdown
    )
    assert "수면" not in report.markdown
    assert "출동" not in report.markdown
    assert "### 움직임\n\n- 상태: GOOD" in report.markdown
    assert "- 설명: 움직임이 2주 전과 비슷하게 유지됐어요." in report.markdown
    assert "- 요약: 움직임 평소 수준" in report.markdown
    assert "### 리모컨 사용\n\n- 상태: GOOD" in report.markdown
    assert "- 움직임 합계" in report.markdown
    assert "- 리모컨 사용 합계" in report.markdown
    assert "- 2주 전과 비교: 112.5%" in report.markdown
    assert "## 3. 기기 데이터 수신" in report.markdown
    assert "## 3. 기기 데이터 수신\n\n- 상태: GOOD" in report.markdown
    assert "- 설명: 모든 데이터가 정상적으로 수집되었어요." in report.markdown
    assert "- 요약: 수신상태 양호" in report.markdown
    assert "- 정상 수신: 7회" in report.markdown
    assert "- 기타 수신 패턴: 0회" in report.markdown
    assert "- 전원 확인 패턴: 0회" in report.markdown
    assert "- 기기 위치 확인 패턴: 0회" in report.markdown
    assert "### 위험 관리 기록" in report.markdown
    assert "상세 기록은 현재 주간 리포트 데이터에 포함되지 않아요." in report.markdown
    assert "# 보호자 행동 제안" in report.markdown
    assert "- 분석: 생활 흐름에 일부 변화가 보였어요." in report.markdown
    assert "- 권장 행동:" not in report.markdown


@pytest.mark.asyncio
async def test_report_requests_power_check_when_device_rows_are_missing() -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    metrics = metrics.model_copy(
        update={
            "current": metrics.current.model_copy(
                update={
                    "covered_days": 0,
                    "daily_summary_count": 0,
                    "device_count": 0,
                    "device_good_count": None,
                    "device_power_count": None,
                    "device_position_count": None,
                }
            ),
            "delta": metrics.delta.model_copy(update={"covered_days": -7}),
        }
    )
    narrative = WeeklyNarrative(
        headline="지난 한 주 생활 흐름을 살펴봤어요.",
        analysis_text="확인된 생활 흐름을 정리했습니다.",
    )

    report = render_report(
        metrics,
        narrative,
        "template_fallback",
        NarrativeGenerationMetadata(
            prompt_version="test",
            validation_status="fallback",
        ),
    )

    assert "## 3. 기기 데이터 수신\n\n- 상태: 자료 없음" in report.markdown
    assert "- 설명: 기기 전원이 연결되어 있는지 확인해 주세요." in report.markdown
    assert "- 정상 수신: 자료 없음" in report.markdown
    assert "- 기타 수신 패턴: 자료 없음" in report.markdown


@pytest.mark.asyncio
async def test_report_labels_available_device_rows_without_claiming_no_data() -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    metrics = metrics.model_copy(
        update={
            "current": metrics.current.model_copy(
                update={
                    "device_good_count": 6,
                    "device_power_count": 0,
                    "device_position_count": 0,
                }
            )
        }
    )
    narrative = WeeklyNarrative(
        headline="지난 한 주 기기 수신 상태는 안정적으로 유지되었습니다.",
        analysis_text=(
            "구체적으로 확인된 기기 데이터는 정상적으로 수집되었습니다."
        ),
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert "## 3. 기기 데이터 수신\n\n- 상태: GOOD" in report.markdown
    assert "- 설명: 모든 데이터가 정상적으로 수집되었어요." in report.markdown
    assert "- 요약: 수신상태 양호" in report.markdown
    assert "- 정상 수신: 6회" in report.markdown
    assert "- 기타 수신 패턴: 1회" in report.markdown
    assert "지난 한 주 기기 데이터 수신이 확인되지 않았어요." not in report.markdown
    assert "기기 전원이 연결되어 있는지 확인해 주세요" not in report.markdown


@pytest.mark.parametrize("night_awake_count", [None, 0.0])
@pytest.mark.asyncio
async def test_report_omits_sleep_section_regardless_of_source_metrics(
    night_awake_count: float | None,
) -> None:
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
                    "night_awake_count_avg": night_awake_count,
                }
            ),
            "previous": metrics.previous.model_copy(
                update={
                    "sleep_time_avg": None,
                    "wake_up_time_avg": None,
                    "night_awake_count_avg": night_awake_count,
                }
            ),
            "delta": metrics.delta.model_copy(
                update={
                    "sleep_time_minutes": None,
                    "wake_up_time_minutes": None,
                    "night_awake_count_avg": (
                        None if night_awake_count is None else 0.0
                    ),
                }
            ),
        }
    )
    narrative = WeeklyNarrative(
        headline="지난 한 주 생활 흐름을 살펴봤어요.",
        analysis_text=(
            "지난 한 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료를 2주 전과 함께 살펴봤어요. "
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
    assert "출동" not in report.markdown
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
        headline="지난 한 주 생활 흐름을 살펴봤어요.",
        analysis_text=(
            "지난 한 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료를 2주 전과 함께 살펴봤어요. "
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

    assert "## 2. 실내 환경\n\n- 상태: GOOD" in report.markdown
    assert "- 설명: 실내 온습도가 대체로 적정 범위에 있었어요." in report.markdown
    assert "- 요약: 쾌적 유지" in report.markdown
    assert "- 온습도 관측일: 7일" in report.markdown
    assert "- 온도 권장범위 이탈: 0일" in report.markdown
    assert "- 습도 권장범위 이탈: 0일" in report.markdown
    assert "15℃ 초과 ~ 31℃ 미만" not in report.markdown
    assert "30% 초과 ~ 70% 미만" not in report.markdown


@pytest.mark.parametrize(
    ("counts", "status", "feedback", "summary"),
    [
        (
            {"temperature_out_of_range_days": 1, "environment_out_of_range_days": 1},
            "GOOD",
            "온도와 습도가 생활하기 좋은 범위에 가까웠어요.",
            "적정 범위",
        ),
        (
            {"temperature_out_of_range_days": 2, "environment_out_of_range_days": 2},
            "CAUTION",
            "실내 온도가 평소보다 불편할 수 있는 구간에 있었어요.",
            "온도 주의",
        ),
        (
            {"humidity_out_of_range_days": 2, "environment_out_of_range_days": 2},
            "CAUTION",
            "실내 습도에 주의가 필요한 시간이 있었어요.",
            "습도 주의",
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_temperature_days": 4,
            },
            "RISK",
            "더운 실내 환경이 반복됐어요.",
            "온습도 확인 필요",
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 4,
            },
            "RISK",
            "권장 온도와 습도 이탈이 여러 날 이어져 냉난방·환기 상태 확인이 필요해요.",
            "온습도 확인 필요",
        ),
    ],
)
@pytest.mark.asyncio
async def test_report_gives_approved_feedback_from_environment_day_counts(
    counts: dict[str, int],
    status: str,
    feedback: str,
    summary: str,
) -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0].model_copy(
        update={"current": source.items[0].current.model_copy(update=counts)}
    )
    narrative = WeeklyNarrative(
        headline="지난 한 주 생활 흐름을 살펴봤어요.",
        analysis_text=(
            "지난 한 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료를 2주 전과 함께 살펴봤어요. "
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
    assert f"- 설명: {feedback}" in report.markdown
    assert f"- 요약: {summary}" in report.markdown


@pytest.mark.parametrize(
    ("average", "score", "status", "description"),
    [
        (
            0.0,
            "0점",
            "RISK",
            "지난 한 주는 즉시 확인이 필요한 위험 신호가 확인됐어요.",
        ),
        (
            25.49,
            "25점",
            "RISK",
            "지난 한 주는 즉시 확인이 필요한 위험 신호가 확인됐어요.",
        ),
        (
            25.5,
            "26점",
            "CAUTION",
            "지난 한 주는 평소와 다른 흐름이 일부 확인됐어요.",
        ),
        (
            75.49,
            "75점",
            "CAUTION",
            "지난 한 주는 평소와 다른 흐름이 일부 확인됐어요.",
        ),
        (
            75.5,
            "76점",
            "GOOD",
            "지난 한 주는 대체로 안정적인 상태가 유지됐어요.",
        ),
        (
            100.0,
            "100점",
            "GOOD",
            "지난 한 주는 대체로 안정적인 상태가 유지됐어요.",
        ),
    ],
)
@pytest.mark.asyncio
async def test_report_classifies_rounded_weekly_average_risk_score(
    average: float,
    score: str,
    status: str,
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
        headline="지난 한 주 생활 흐름을 살펴봤어요.",
        analysis_text=(
            "지난 한 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료를 2주 전과 함께 살펴봤어요. "
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
    assert f"- 상태: {status}" in report.markdown
    assert f"- 상태 안내: {description}" in report.markdown


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
        headline="지난 한 주 생활 흐름을 살펴봤어요.",
        analysis_text=(
            "지난 한 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료를 2주 전과 함께 살펴봤어요. "
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
    assert "- 상태: 자료 없음" in report.markdown
    assert (
        "지난 한 주 상태 점수를 계산할 자료가 없어요."
        in report.markdown
    )
