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
            "집 안 온도와 습도가 대체로 쾌적하게 유지됐어요.",
            "쾌적",
        ),
        (
            {
                "temperature_out_of_range_days": 1,
                "environment_out_of_range_days": 1,
                "high_temperature_days": 1,
            },
            "GOOD",
            1,
            "집 안 온도와 습도가 대체로 쾌적하게 유지됐어요.",
            "쾌적",
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "high_temperature_days": 2,
            },
            "CAUTION",
            1,
            "집 안이 조금 더운 날이 있었어요. 냉방이나 환기 상태를 한 번 살펴봐 주세요.",
            "조금 더움",
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "low_temperature_days": 2,
            },
            "CAUTION",
            2,
            "집 안이 조금 추운 날이 있었어요. 난방 상태를 한 번 확인해 주세요.",
            "조금 추움",
        ),
        (
            {
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "high_humidity_days": 2,
            },
            "CAUTION",
            3,
            "집 안이 습한 날이 있었어요. 제습이나 환기가 필요한지 살펴봐 주세요.",
            "습함",
        ),
        (
            {
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "low_humidity_days": 2,
            },
            "CAUTION",
            4,
            "집 안이 건조한 날이 있었어요. 너무 건조하지 않은지 한 번 살펴봐 주세요.",
            "건조함",
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "high_temperature_days": 2,
                "high_humidity_days": 2,
            },
            "CAUTION",
            5,
            "덥고 습한 날이 있었어요. 냉방과 환기가 잘 되고 있는지 함께 살펴봐 주세요.",
            "덥고 습함",
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "high_temperature_days": 2,
                "low_humidity_days": 2,
            },
            "CAUTION",
            6,
            "집 안이 덥고 건조한 날이 있었어요. 냉방 상태와 실내 습도를 함께 살펴봐 주세요.",
            "덥고 건조함",
        ),
        (
            {
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "cool_temperature_days": 2,
                "high_humidity_days": 2,
                "humidity_at_or_above_70_days": 2,
            },
            "CAUTION",
            7,
            "집 안이 다소 서늘하고 습한 날이 있었어요. 난방과 환기 상태를 함께 살펴봐 주세요.",
            "서늘하고 습함",
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "low_temperature_days": 2,
                "low_humidity_days": 2,
            },
            "CAUTION",
            8,
            "집 안이 춥고 건조한 날이 있었어요. 난방 상태와 실내 습도를 함께 살펴봐 주세요.",
            "춥고 건조함",
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_temperature_days": 4,
            },
            "RISK",
            1,
            "집 안이 많이 더운 날이 여러 번 이어졌어요. 냉방이 잘 되고 있는지 조금 더 세심하게 살펴봐 주세요.",
            "더운 날 이어짐",
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "low_temperature_days": 4,
            },
            "RISK",
            2,
            "집 안이 추운 날이 여러 번 이어졌어요. 난방 상태와 생활에 불편함은 없는지 살펴봐 주세요.",
            "추운 날 이어짐",
        ),
        (
            {
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_humidity_days": 4,
            },
            "RISK",
            3,
            "습한 날이 여러 번 이어졌어요. 제습이나 환기가 잘 되고 있는지 살펴봐 주세요.",
            "습한 날 이어짐",
        ),
        (
            {
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "low_humidity_days": 4,
            },
            "RISK",
            4,
            "건조한 날이 여러 번 이어졌어요. 집 안이 너무 건조하지 않은지 살펴봐 주세요.",
            "건조한 날 이어짐",
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_temperature_days": 4,
                "high_humidity_days": 4,
            },
            "RISK",
            5,
            "덥고 습한 날이 여러 번 이어졌어요. 냉방과 환기가 잘 되고 있는지 조금 더 세심하게 살펴봐 주세요.",
            "덥고 습한 날 이어짐",
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_temperature_days": 4,
                "low_humidity_days": 4,
            },
            "RISK",
            6,
            "덥고 건조한 날이 여러 번 이어졌어요. 냉방 상태와 실내 습도를 함께 살펴봐 주세요.",
            "덥고 건조한 날 이어짐",
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "low_temperature_days": 4,
                "cool_temperature_days": 4,
                "humidity_at_or_above_70_days": 4,
            },
            "RISK",
            7,
            "춥고 습한 날이 여러 번 이어졌어요. 난방과 환기 상태를 함께 살펴봐 주세요.",
            "춥고 습한 날 이어짐",
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "low_temperature_days": 4,
                "low_humidity_days": 4,
            },
            "RISK",
            8,
            "춥고 건조한 날이 여러 번 이어졌어요. 난방 상태와 실내 습도를 조금 더 세심하게 살펴봐 주세요.",
            "춥고 건조한 날 이어짐",
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
                "high_temperature_days": 1,
            },
            "GOOD",
            1,
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "high_temperature_days": 2,
            },
            "CAUTION",
            1,
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "high_temperature_days": 2,
                "low_humidity_days": 2,
            },
            "CAUTION",
            6,
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_temperature_days": 4,
                "high_humidity_days": 4,
            },
            "RISK",
            5,
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


def test_combined_four_day_risk_selects_directional_sheet_variant() -> None:
    assessment = assess_environment(
        _metrics(
            temperature_out_of_range_days=4,
            humidity_out_of_range_days=4,
            environment_out_of_range_days=4,
            low_humidity_days=4,
            high_temperature_days=4,
        )
    )

    assert (assessment.status, assessment.variant) == ("RISK", 6)


def test_environment_policy_discloses_missing_daily_extrema_counts() -> None:
    assessment = assess_environment(
        _metrics(
            environment_observed_days=None,
            temperature_out_of_range_days=None,
            humidity_out_of_range_days=None,
            environment_out_of_range_days=None,
            low_temperature_days=None,
            cool_temperature_days=None,
            high_temperature_days=None,
            low_humidity_days=None,
            high_humidity_days=None,
            humidity_at_or_above_70_days=None,
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
    assert any("건조한 날이 여러 번" in fact for fact in facts.facts)
    narrative = build_fallback(facts)
    summary = f"{narrative.headline} {narrative.analysis_text}"
    assert "생활 정보가 빠짐없이" in summary
    assert "건조한 날" in summary

    messages = build_messages(facts)
    assert PROMPT_VERSION == "weekly-korean-free-summary-v21"
    assert len(messages) == 1
    assert "총평 본문만 출력합니다" in messages[0]["content"]
    assert '"실내 환경"' in messages[0]["content"]
    assert "건조한 날이 여러 번" in messages[0]["content"]
    assert "summary_outline" not in messages[0]["content"]


@pytest.mark.asyncio
async def test_reporter_rejects_analysis_that_omits_required_environment() -> None:
    facts = build_fact_package(
        _metrics(
            temperature_out_of_range_days=2,
            environment_out_of_range_days=2,
        )
    )
    missing_environment = (
        "지난 한 주 대상님은 평소와 비슷한 생활 흐름을 이어가셨어요. "
        "생활 활동과 TV 이용 등 일상적인 생활 패턴도 비슷했어요. "
        "생활 정보도 빠짐없이 잘 들어왔어요."
    )

    class OmittingModel:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, *args: object, **kwargs: object) -> str:
            self.calls += 1
            return missing_environment

    model = OmittingModel()
    narrative, mode, metadata = await generate_narrative(model, facts)

    assert model.calls == 2
    assert mode == "template_fallback"
    assert metadata.fallback_reason == "invalid_narrative_content"
    assert "집 안" in narrative.analysis_text
