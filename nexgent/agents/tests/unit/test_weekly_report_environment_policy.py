import json
from datetime import date, timedelta

import pytest
from ax_contracts import WardWeeklyMetrics

from workflows.weekly_report.agents.reporter.fallback import build_fallback
from workflows.weekly_report.agents.reporter.narrative import generate_narrative
from workflows.weekly_report.agents.reporter.prompt import (
    PROMPT_VERSION,
    build_messages,
)
from workflows.weekly_report.domain.derived_metrics import build_fact_package
from workflows.weekly_report.domain.environment_policy import (
    assess_environment,
    environment_description,
    environment_summary,
)
from workflows.weekly_report.tools.source_repository import _mock_delta, _snapshot


def _metrics(*, month: int = 8, **counts: int | None) -> WardWeeklyMetrics:
    current = _snapshot(101, current=True).model_copy(update=counts)
    previous = _snapshot(101, current=False)
    week_start = date(2026, month, 1)
    return WardWeeklyMetrics(
        ward_id=101,
        display_name="대상",
        week_start=week_start,
        week_end=week_start + timedelta(days=7),
        current=current,
        previous=previous,
        delta=_mock_delta(current, previous),
    )


@pytest.mark.parametrize("month", [1, 4, 8, 12])
def test_environment_policy_uses_year_round_strict_ranges(month: int) -> None:
    assessment = assess_environment(_metrics(month=month))

    assert (assessment.temperature_low, assessment.temperature_high) == (15, 31)
    assert (assessment.humidity_low, assessment.humidity_high) == (30, 70)


@pytest.mark.parametrize(
    (
        "counts",
        "status",
        "variant",
        "description",
        "summary",
    ),
    [
        (
            {},
            "GOOD",
            1,
            "실내 온습도가 대체로 적정 범위에 있었어요.",
            "쾌적 유지",
        ),
        (
            {"temperature_out_of_range_days": 1, "environment_out_of_range_days": 1},
            "GOOD",
            2,
            "온도와 습도가 생활하기 좋은 범위에 가까웠어요.",
            "적정 범위",
        ),
        (
            {"humidity_out_of_range_days": 2, "environment_out_of_range_days": 2},
            "CAUTION",
            1,
            "실내 습도에 주의가 필요한 시간이 있었어요.",
            "습도 주의",
        ),
        (
            {"temperature_out_of_range_days": 2, "environment_out_of_range_days": 2},
            "CAUTION",
            2,
            "실내 온도가 평소보다 불편할 수 있는 구간에 있었어요.",
            "온도 주의",
        ),
        (
            {
                "temperature_out_of_range_days": 1,
                "humidity_out_of_range_days": 1,
                "environment_out_of_range_days": 2,
            },
            "CAUTION",
            3,
            "온도나 습도 변화가 며칠간 이어져 확인이 필요해요.",
            "온습도 주의",
        ),
        (
            {
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "low_humidity_days": 4,
            },
            "RISK",
            1,
            "건조한 실내 환경이 반복됐어요.",
            "습도 확인 필요",
        ),
        (
            {
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_humidity_days": 4,
            },
            "RISK",
            2,
            "습한 실내 환경이 반복됐어요.",
            "습도 확인 필요",
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "low_temperature_days": 4,
            },
            "RISK",
            3,
            "추운 실내 환경이 반복됐어요.",
            "온도 확인 필요",
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_temperature_days": 4,
            },
            "RISK",
            4,
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
            5,
            "권장 온도와 습도 이탈이 여러 날 이어져 냉난방·환기 상태 확인이 필요해요.",
            "온습도 확인 필요",
        ),
    ],
)
def test_environment_policy_uses_exact_approved_copy(
    counts: dict[str, int],
    status: str,
    variant: int,
    description: str,
    summary: str,
) -> None:
    assessment = assess_environment(_metrics(**counts))

    assert assessment.status == status
    assert assessment.variant == variant
    assert environment_description(assessment) == description
    assert environment_summary(assessment) == summary


@pytest.mark.parametrize(
    ("counts", "expected_status", "expected_variant"),
    [
        ({"environment_out_of_range_days": 0}, "GOOD", 1),
        (
            {
                "temperature_out_of_range_days": 1,
                "environment_out_of_range_days": 1,
            },
            "GOOD",
            2,
        ),
        (
            {
                "temperature_out_of_range_days": 1,
                "humidity_out_of_range_days": 1,
                "environment_out_of_range_days": 2,
            },
            "CAUTION",
            3,
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 3,
            },
            "CAUTION",
            3,
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 4,
            },
            "RISK",
            5,
        ),
        (
            {
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
            },
            "CAUTION",
            1,
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
            },
            "CAUTION",
            2,
        ),
    ],
)
def test_environment_status_uses_approved_departure_day_bands(
    counts: dict[str, int],
    expected_status: str,
    expected_variant: int,
) -> None:
    assessment = assess_environment(_metrics(**counts))

    assert (assessment.status, assessment.variant) == (
        expected_status,
        expected_variant,
    )


@pytest.mark.parametrize(
    ("directional_count", "expected_status"),
    [(3, "CAUTION"), (4, "RISK")],
)
def test_environment_directional_extreme_requires_four_repeated_days(
    directional_count: int,
    expected_status: str,
) -> None:
    assessment = assess_environment(
        _metrics(
            humidity_out_of_range_days=directional_count,
            environment_out_of_range_days=directional_count,
            low_humidity_days=directional_count,
        )
    )

    assert assessment.status == expected_status


def test_combined_four_day_risk_takes_precedence_over_directional_risk() -> None:
    assessment = assess_environment(
        _metrics(
            temperature_out_of_range_days=4,
            humidity_out_of_range_days=4,
            environment_out_of_range_days=4,
            low_humidity_days=4,
            high_temperature_days=4,
        )
    )

    assert (assessment.status, assessment.variant) == ("RISK", 5)


def test_environment_policy_discloses_missing_daily_extrema_counts() -> None:
    assessment = assess_environment(
        _metrics(
            environment_observed_days=None,
            temperature_out_of_range_days=None,
            humidity_out_of_range_days=None,
            environment_out_of_range_days=None,
            low_temperature_days=None,
            high_temperature_days=None,
            low_humidity_days=None,
            high_humidity_days=None,
        )
    )

    assert assessment.status == "UNAVAILABLE"
    assert assessment.variant is None
    assert environment_description(assessment) == (
        "지난 한 주 실내 온습도 상태를 판단할 자료가 부족해요."
    )


def test_environment_facts_are_required_in_weekly_analysis() -> None:
    facts = build_fact_package(
        _metrics(
            humidity_out_of_range_days=4,
            environment_out_of_range_days=4,
            low_humidity_days=4,
        )
    )

    assert "실내 환경" in facts.required_topics
    assert any("건조한 환경이 반복" in fact for fact in facts.facts)
    analysis = build_fallback(facts).analysis_text
    assert "실내 온도와 습도" in analysis
    assert "건조한 환경" in analysis
    assert "움직임" not in analysis
    assert "기기 데이터" not in analysis

    messages = build_messages(facts)
    assert PROMPT_VERSION == "weekly-korean-valuable-insights-v14"
    assert (
        "required_topics는 반드시 전달해야 하는 중요한 이슈입니다"
        in messages[0]["content"]
    )
    assert "모든 사실을 기계적으로 나열하지 마세요" in messages[0]["content"]
    assert "영역별 사실을 끊어진 목록처럼 나열하지 마세요" in messages[0]["content"]
    assert "facts에 자료 부족이 명시된 영역은 생략하지 말고" in messages[0]["content"]
    assert "첫 문장부터 “구체적으로”" in messages[0]["content"]
    assert "한주 총평 전체에서 이 첫 문장에만 한 번" in messages[0]["content"]
    assert "불안이나 긴박감을 높이는 표현" in messages[0]["content"]
    assert "수면과 출동은 이 보고서의 제외 영역" in messages[0]["content"]
    assert "비교 대상 기간은 반드시 “2주 전”" in messages[0]["content"]
    assert "안심지키미 서비스의" in messages[0]["content"]
    assert "한국어 고객지원 및 보호자 커뮤니케이션 전문가" in messages[0]["content"]
    assert "부모님 등 고령의 가족" in messages[0]["content"]
    assert "section_assessments" in messages[0]["content"]
    assert "수면" not in messages[1]["content"]
    assert "출동" not in messages[1]["content"]
    assert '"summary_outline"' in messages[1]["content"]
    assert '"section_assessments"' in messages[1]["content"]
    assert '"guardian_action_candidates"' in messages[1]["content"]
    assert '"실내 환경"' in messages[1]["content"]


@pytest.mark.asyncio
async def test_reporter_rejects_analysis_that_omits_required_environment() -> None:
    facts = build_fact_package(
        _metrics(
            temperature_out_of_range_days=2,
            environment_out_of_range_days=2,
        )
    )
    fallback = build_fallback(facts)
    missing_environment = fallback.model_copy(
        update={
            "analysis_text": "지난 한 주 생활 흐름은 전반적으로 차분하게 이어졌습니다."
        }
    )

    class OmittingModel:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, *args: object, **kwargs: object) -> str:
            self.calls += 1
            return json.dumps(missing_environment.model_dump(), ensure_ascii=False)

    model = OmittingModel()
    narrative, mode, metadata = await generate_narrative(model, facts)

    assert model.calls == 2
    assert mode == "template_fallback"
    assert metadata.fallback_reason == "invalid_narrative_content"
    assert "온도" in narrative.analysis_text
