import json
from datetime import date, time

import pytest
from ax_contracts import WardWeeklyMetrics

from workflows.weekly_report.agents.reporter.fallback import build_fallback
from workflows.weekly_report.agents.reporter.narrative import generate_narrative
from workflows.weekly_report.domain.derived_metrics import build_fact_package
from workflows.weekly_report.domain.models import FactPackage
from workflows.weekly_report.source.calculator import (
    _device_reception_counts,
    _environment_day_counts,
    calculate_metrics,
)
from workflows.weekly_report.tools.source_repository import _mock_delta, _snapshot


def test_calculator_matches_weighted_and_linear_average_semantics() -> None:
    rows = [
        {
            "ward_id": 1,
            "device_id": 10,
            "date": date(2026, 8, 3),
            "temperature": 20,
            "temperature_count": 1,
            "humidity": 40,
            "humidity_count": 2,
            "light": 100,
            "light_count": 1,
            "min_temperature": 18,
            "max_temperature": 22,
            "min_humidity": 35,
            "max_humidity": 45,
            "min_light": 10,
            "max_light": 200,
            "light_on_time_minutes": 300,
            "movement_count": 10,
            "remote_control_count": 2,
            "wake_up_time": time(7),
            "sleep_time": time(22),
            "night_awake_count": 1,
        },
        {
            "ward_id": 1,
            "device_id": 10,
            "date": date(2026, 8, 4),
            "temperature": 30,
            "temperature_count": 3,
            "humidity": 50,
            "humidity_count": 2,
            "light": 200,
            "light_count": 1,
            "min_temperature": 25,
            "max_temperature": 32,
            "min_humidity": 45,
            "max_humidity": 55,
            "min_light": 20,
            "max_light": 300,
            "light_on_time_minutes": 500,
            "movement_count": 20,
            "remote_control_count": 4,
            "wake_up_time": time(9),
            "sleep_time": time(23),
            "night_awake_count": 3,
        },
    ]
    metrics = calculate_metrics(
        ward_names={1: "대상"},
        week_start=date(2026, 8, 3),
        daily_rows=rows,
        risk_rows=[
            {
                "ward_id": 1,
                "period_index": 1,
                "risk_detected_count": 2,
                "risk_resolved_count": 1,
                "risk_score_avg": 0.4,
                "danger_days": 1,
            }
        ],
        dispatch_rows=[],
    )[0]
    assert metrics.current.temperature_avg == 27.5
    assert metrics.current.movement_count_avg == 15
    assert metrics.current.movement_count_total == 30
    assert metrics.current.remote_control_count_total == 6
    assert metrics.current.environment_observed_days == 2
    assert metrics.current.temperature_out_of_range_days == 1
    assert metrics.current.humidity_out_of_range_days == 0
    assert metrics.current.environment_out_of_range_days == 1
    assert metrics.current.low_temperature_days == 0
    assert metrics.current.cool_temperature_days == 0
    assert metrics.current.high_temperature_days == 1
    assert metrics.current.low_humidity_days == 0
    assert metrics.current.high_humidity_days == 0
    assert metrics.current.humidity_at_or_above_70_days == 0
    assert metrics.current.device_good_count == 0
    assert metrics.current.device_power_count == 0
    assert metrics.current.device_position_count == 2
    assert metrics.current.wake_up_time_avg == time(8)
    assert metrics.current.covered_days == 2
    assert metrics.current.risk_detected_count == 2


@pytest.mark.parametrize(
    ("field", "overrides"),
    [
        ("low_humidity_days", {"min_humidity": 20, "max_humidity": 29.9}),
        ("high_humidity_days", {"min_humidity": 50, "max_humidity": 70.1}),
        ("low_temperature_days", {"min_temperature": 10, "max_temperature": 14.9}),
        ("high_temperature_days", {"min_temperature": 27, "max_temperature": 31.1}),
    ],
)
def test_environment_risk_direction_counts_use_daily_maximum_extreme_thresholds(
    field: str,
    overrides: dict[str, float],
) -> None:
    rows = [
        {
            "date": date(2026, 8, 3 + offset),
            "min_temperature": 26,
            "max_temperature": 27,
            "min_humidity": 40,
            "max_humidity": 50,
            **overrides,
        }
        for offset in range(4)
    ]

    counts = _environment_day_counts(rows)

    assert counts[field] == 4


@pytest.mark.parametrize(
    ("field", "departure_field", "overrides"),
    [
        (
            "low_humidity_days",
            "humidity_out_of_range_days",
            {"min_humidity": 20, "max_humidity": 30},
        ),
        (
            "high_humidity_days",
            "humidity_out_of_range_days",
            {"min_humidity": 50, "max_humidity": 70},
        ),
        (
            "low_temperature_days",
            "temperature_out_of_range_days",
            {"min_temperature": 10, "max_temperature": 15},
        ),
        (
            "high_temperature_days",
            "temperature_out_of_range_days",
            {"min_temperature": 27, "max_temperature": 31},
        ),
    ],
)
def test_environment_exact_boundaries_are_inside_the_sheet_range(
    field: str,
    departure_field: str,
    overrides: dict[str, float],
) -> None:
    rows = [
        {
            "date": date(2026, 8, 3 + offset),
            "min_temperature": 26,
            "max_temperature": 27,
            "min_humidity": 40,
            "max_humidity": 50,
            **overrides,
        }
        for offset in range(4)
    ]

    counts = _environment_day_counts(rows)

    assert counts[field] == 0
    assert counts[departure_field] == 0


def test_environment_special_combined_thresholds_use_daily_maxima() -> None:
    rows = [
        {
            "date": date(2026, 8, 3 + offset),
            "min_temperature": 10,
            "max_temperature": 17.9,
            "min_humidity": 40,
            "max_humidity": 70,
        }
        for offset in range(4)
    ]

    counts = _environment_day_counts(rows)

    assert counts["low_temperature_days"] == 0
    assert counts["cool_temperature_days"] == 4
    assert counts["high_humidity_days"] == 0
    assert counts["humidity_at_or_above_70_days"] == 4


def test_environment_special_combined_thresholds_keep_exact_18_exclusive() -> None:
    counts = _environment_day_counts(
        [
            {
                "date": date(2026, 8, 3),
                "min_temperature": 10,
                "max_temperature": 18,
                "min_humidity": 40,
                "max_humidity": 69.9,
            }
        ]
    )

    assert counts["cool_temperature_days"] == 0
    assert counts["humidity_at_or_above_70_days"] == 0


def test_environment_values_strictly_inside_recommended_ranges_are_not_departures() -> (
    None
):
    rows = [
        {
            "date": date(2026, 8, 3),
            "min_temperature": 15.1,
            "max_temperature": 30.9,
            "min_humidity": 30.1,
            "max_humidity": 69.9,
        }
    ]

    counts = _environment_day_counts(rows)

    assert counts["temperature_out_of_range_days"] == 0
    assert counts["humidity_out_of_range_days"] == 0
    assert counts["environment_out_of_range_days"] == 0


def test_device_reception_calculation_prioritizes_low_counts() -> None:
    counts = _device_reception_counts(
        [
            {
                "temperature_count": 20,
                "humidity_count": 20,
                "light_count": 20,
                "remote_control_count": 20,
                "movement_count": 20,
            },
            {
                "temperature_count": None,
                "humidity_count": None,
                "light_count": None,
                "remote_control_count": 25,
                "movement_count": 40,
            },
            {
                "temperature_count": None,
                "humidity_count": None,
                "light_count": None,
                "remote_control_count": 0,
                "movement_count": 0,
            },
            {
                "temperature_count": 5,
                "humidity_count": 5,
                "light_count": 20,
                "remote_control_count": 20,
                "movement_count": 20,
            },
        ]
    )

    assert counts == {
        "device_good_count": 1,
        "device_power_count": 1,
        "device_position_count": 2,
    }


def test_device_good_ignores_remote_control_but_requires_temperature() -> None:
    counts = _device_reception_counts(
        [
            {
                "temperature_count": 20,
                "humidity_count": 20,
                "light_count": 20,
                "remote_control_count": 0,
                "movement_count": 20,
            },
            {
                "temperature_count": 0,
                "humidity_count": 20,
                "light_count": 20,
                "remote_control_count": 20,
                "movement_count": 20,
            },
        ]
    )

    assert counts == {
        "device_good_count": 1,
        "device_power_count": 0,
        "device_position_count": 0,
    }


def test_device_power_depends_only_on_three_measurement_counts() -> None:
    counts = _device_reception_counts(
        [
            {
                "temperature_count": None,
                "humidity_count": None,
                "light_count": None,
                "remote_control_count": 25,
                "movement_count": 40,
            }
        ]
    )

    assert counts == {
        "device_good_count": 0,
        "device_power_count": 1,
        "device_position_count": 0,
    }


def test_device_position_range_is_inclusive_and_null_is_not_low() -> None:
    counts = _device_reception_counts(
        [
            {
                "temperature_count": 0,
                "humidity_count": 10,
                "light_count": 20,
                "remote_control_count": 20,
                "movement_count": 20,
            },
            {
                "temperature_count": None,
                "humidity_count": 10.1,
                "light_count": 20,
                "remote_control_count": 20,
                "movement_count": 20,
            },
        ]
    )

    assert counts["device_position_count"] == 1


def test_device_reception_rows_check_position_before_power_and_good() -> None:
    counts = _device_reception_counts(
        [
            {
                "temperature_count": 5,
                "humidity_count": 5,
                "light_count": 5,
                "remote_control_count": 5,
                "movement_count": 5,
            },
            {
                "temperature_count": None,
                "humidity_count": None,
                "light_count": None,
                "remote_control_count": 0,
                "movement_count": 0,
            },
            {
                "temperature_count": 0,
                "humidity_count": 10,
                "light_count": 20,
                "remote_control_count": 20,
                "movement_count": 20,
            },
        ]
    )

    assert counts == {
        "device_good_count": 0,
        "device_power_count": 0,
        "device_position_count": 3,
    }


def test_fact_package_prioritizes_available_facts_over_coverage_disclosure() -> None:
    current = _snapshot(103, current=True).model_copy(update={"covered_days": 4})
    previous = _snapshot(103, current=False)

    metrics = WardWeeklyMetrics(
        ward_id=103,
        display_name="대상",
        week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10),
        current=current,
        previous=previous,
        delta=_mock_delta(current, previous),
    )
    facts = build_fact_package(metrics)
    assert facts.coverage == "incomplete"
    assert facts.required_topics == []
    assert "자료 상태" in facts.allowed_topics
    assert facts.weekly_report_data is not None
    assert facts.weekly_report_data.subscriber == "대상"
    assert len(facts.suggested_actions) <= 3


@pytest.mark.asyncio
async def test_reporter_rejects_code_fenced_output_and_uses_fallback() -> None:
    current = _snapshot(101, current=True)
    previous = _snapshot(101, current=False)
    facts = build_fact_package(
        WardWeeklyMetrics(
            ward_id=101,
            display_name="대상",
            week_start=date(2026, 8, 3),
            week_end=date(2026, 8, 10),
            current=current,
            previous=previous,
            delta=_mock_delta(current, previous),
        )
    )
    expected = build_fallback(facts)

    class FencedJsonModel:
        async def complete(self, *args: object, **kwargs: object) -> str:
            payload = json.dumps(expected.model_dump(mode="json"), ensure_ascii=False)
            return f"```json\n{payload}\n```"

    narrative, mode, metadata = await generate_narrative(FencedJsonModel(), facts)

    assert narrative == expected
    assert mode == "template_fallback"
    assert metadata.validation_status == "fallback"


@pytest.mark.asyncio
async def test_reporter_gives_specific_sentence_feedback_before_retry() -> None:
    current = _snapshot(101, current=True)
    previous = _snapshot(101, current=False)
    facts = build_fact_package(
        WardWeeklyMetrics(
            ward_id=101,
            display_name="대상",
            week_start=date(2026, 8, 3),
            week_end=date(2026, 8, 10),
            current=current,
            previous=previous,
            delta=_mock_delta(current, previous),
        )
    )
    expected = build_fallback(facts)
    expected_text = f"{expected.headline} {expected.analysis_text}"

    class CorrectingModel:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(
            self, messages: list[dict[str, str]], **kwargs: object
        ) -> str:
            self.calls += 1
            if self.calls == 1:
                return "지난 한 주 생활 흐름을 살펴봤어요.\n생활 정보도 확인했어요."
            assert "한 문단" in messages[-1]["content"]
            return expected_text

    model = CorrectingModel()
    narrative, mode, metadata = await generate_narrative(model, facts)

    assert model.calls == 2
    assert narrative == expected
    assert mode == "llm"
    assert metadata.validation_status == "passed"


@pytest.mark.asyncio
async def test_reporter_retries_formal_summary_in_warm_haeyo_register() -> None:
    current = _snapshot(101, current=True)
    previous = _snapshot(101, current=False)
    facts = build_fact_package(
        WardWeeklyMetrics(
            ward_id=101,
            display_name="대상",
            week_start=date(2026, 8, 3),
            week_end=date(2026, 8, 10),
            current=current,
            previous=previous,
            delta=_mock_delta(current, previous),
        )
    )
    expected = build_fallback(facts)
    expected_text = f"{expected.headline} {expected.analysis_text}"
    formal = "지난 한 주 대상님은 생활 흐름을 유지했습니다. 생활 정보도 확인되었습니다."

    class WarmingModel:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(
            self, messages: list[dict[str, str]], **kwargs: object
        ) -> str:
            self.calls += 1
            if self.calls == 1:
                return formal
            assert "부드러운 해요체" in messages[-1]["content"]
            return expected_text

    model = WarmingModel()
    narrative, mode, metadata = await generate_narrative(model, facts)

    assert model.calls == 2
    assert narrative == expected
    assert mode == "llm"
    assert metadata.validation_status == "passed"


@pytest.mark.asyncio
async def test_reporter_rejects_unsupported_topic_then_uses_fallback() -> None:
    current = _snapshot(101, current=True)
    previous = _snapshot(101, current=False)
    facts = build_fact_package(
        WardWeeklyMetrics(
            ward_id=101,
            display_name="대상",
            week_start=date(2026, 8, 3),
            week_end=date(2026, 8, 10),
            current=current,
            previous=previous,
            delta=_mock_delta(current, previous),
        )
    )
    unsupported = "지난 한 주 대상님은 생활 흐름을 이어가셨어요. 출동 요청도 확인했어요."

    class UnsupportedModel:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, *args: object, **kwargs: object) -> str:
            self.calls += 1
            return unsupported

    model = UnsupportedModel()
    narrative, mode, metadata = await generate_narrative(model, facts)
    assert model.calls == 2
    assert mode == "template_fallback"
    assert metadata.fallback_reason == "invalid_narrative_content"
    assert "출동" not in narrative.analysis_text


def test_fallback_uses_one_available_fact_without_padding() -> None:
    facts = FactPackage(
        coverage="incomplete",
        facts=["움직임이 2주 전보다 줄어든 흐름이 보여요."],
        allowed_topics=["활동"],
        required_topics=["활동"],
        suggested_actions=[],
    )

    narrative = build_fallback(facts)

    expected = "움직임이 2주 전보다 줄어든 흐름이 보였습니다."
    assert narrative.headline == expected
    assert narrative.analysis_text == expected
    assert narrative.observations == [expected]
    assert narrative.suggestions == []


@pytest.mark.asyncio
async def test_reporter_rejects_unrelated_missing_data_filler() -> None:
    current = _snapshot(101, current=True)
    previous = _snapshot(101, current=False)
    facts = build_fact_package(
        WardWeeklyMetrics(
            ward_id=101,
            display_name="대상",
            week_start=date(2026, 8, 3),
            week_end=date(2026, 8, 10),
            current=current,
            previous=previous,
            delta=_mock_delta(current, previous),
        )
    )
    unrelated = "지난 한 주 생활 요약 안내드립니다. 다음 주에는 더 잘 살펴볼게요."

    class UnrelatedModel:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, *args: object, **kwargs: object) -> str:
            self.calls += 1
            return unrelated

    model = UnrelatedModel()
    narrative, mode, metadata = await generate_narrative(model, facts)

    assert model.calls == 2
    assert mode == "template_fallback"
    assert metadata.fallback_reason == "invalid_narrative_content"
    assert "생활 요약 안내드립니다" not in (
        f"{narrative.headline} {narrative.analysis_text}"
    )


def test_fallback_builds_formal_insight_summary_from_weekly_facts() -> None:
    facts = FactPackage(
        coverage="complete",
        facts=[
            "생활 정보가 빠짐없이 잘 들어왔어요.",
            "권장 온도와 습도 이탈이 여러 날 이어져 냉난방·환기 상태 확인이 필요해요.",
            "움직임이 2주 전과 비슷하게 유지됐어요.",
            "리모컨 사용이 2주 전과 비슷했어요.",
        ],
        allowed_topics=["기기 상태", "실내 환경", "활동"],
        required_topics=["기기 상태", "실내 환경", "활동"],
        suggested_actions=["생활 환경을 확인해 주세요"],
    )

    narrative = build_fallback(facts)

    assert narrative.headline == (
        "움직임과 리모컨 사용량은 2주 전과 비슷하게 유지되었습니다."
    )
    assert narrative.analysis_text == (
        "생활 정보가 빠짐없이 잘 들어왔습니다. "
        "움직임과 리모컨 사용량은 2주 전과 비슷하게 유지되었습니다. "
        "다만 권장 온도와 습도 이탈이 여러 날 이어져 "
        "냉난방·환기 상태 확인이 필요합니다."
    )
    assert narrative.suggestions == ["생활 환경을 확인해 주세요"]
