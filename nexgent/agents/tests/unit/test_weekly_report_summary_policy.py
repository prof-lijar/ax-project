from datetime import date

import pytest
from ax_contracts import (
    WardWeeklyMetricDelta,
    WardWeeklyMetrics,
    WardWeeklyMetricSnapshot,
    WeeklyNarrative,
)

from workflows.weekly_report.agents.reporter.fallback import build_fallback
from workflows.weekly_report.agents.reporter.policy import validate_narrative
from workflows.weekly_report.domain.derived_metrics import build_fact_package
from workflows.weekly_report.domain.summary_policy import build_weekly_summary_outline
from workflows.weekly_report.tools.source_repository import _mock_delta, _snapshot


def _metrics(
    *,
    current_updates: dict[str, int | float | None] | None = None,
    previous_updates: dict[str, int | float | None] | None = None,
) -> WardWeeklyMetrics:
    current = _snapshot(101, current=True).model_copy(update=current_updates or {})
    previous = _snapshot(101, current=False).model_copy(update=previous_updates or {})
    return WardWeeklyMetrics(
        ward_id=101,
        display_name="대상",
        week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10),
        current=current,
        previous=previous,
        delta=_mock_delta(current, previous),
    )


def test_all_good_outline_covers_report_areas_and_close() -> None:
    facts = build_fact_package(_metrics())
    outline = facts.summary_outline

    assert outline is not None
    assert outline.mode == "ALL_GOOD"
    assert outline.data_quality_code == "VALID"
    assert outline.good_topic_list == ["활동", "환경", "기기"]
    assert facts.required_topics == []
    narrative = build_fallback(facts)
    assert "움직임과 리모컨" in narrative.analysis_text
    assert "온도와 습도" in narrative.analysis_text
    assert "기기 데이터" in narrative.analysis_text
    assert "수면" not in narrative.analysis_text
    assert "출동" not in narrative.analysis_text
    assert outline.close.startswith("이번 주에는")


def test_low_data_mode_puts_evaluated_day_scope_first_without_risk_inference() -> None:
    facts = build_fact_package(_metrics(current_updates={"covered_days": 3}))
    outline = facts.summary_outline

    assert outline is not None
    assert outline.mode == "LOW_DATA"
    assert outline.data_quality_code == "LOW_DATA"
    assert outline.valid_days == 3
    assert outline.headline == (
        "지난 한 주 대상님의 생활은 확인된 자료 범위 안에서 "
        "세심하게 살펴보았습니다."
    )
    assert "위험" not in outline.headline
    assert "자료 상태" in facts.allowed_topics
    assert build_fallback(facts).headline == outline.headline
    assert outline.close == (
        "이번 주에는 기기 전원 연결 상태를 확인해 주시고, "
        "생활환경을 함께 살펴봐 주세요."
    )


def test_no_sensor_data_produces_connected_section_insights() -> None:
    metrics = WardWeeklyMetrics(
        ward_id=101,
        display_name="대상",
        week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10),
        current=WardWeeklyMetricSnapshot(),
        previous=WardWeeklyMetricSnapshot(),
        delta=WardWeeklyMetricDelta(danger_days=0),
    )

    facts = build_fact_package(metrics)
    narrative = build_fallback(facts)

    assert facts.summary_outline is not None
    assert facts.summary_outline.available_item_list == [
        "움직임",
        "리모컨",
        "실내 환경",
        "기기 데이터 수신",
    ]
    assert narrative.analysis_text == (
        "구체적으로 움직임과 리모컨 사용량은 2주 전과 비교할 자료가 부족합니다. "
        "이와 함께 실내 온도와 습도 상태를 판단할 자료가 부족합니다. "
        "또한 기기 데이터 수신이 확인되지 않아 전원 연결 상태를 확인할 필요가 있습니다."
    )
    assert (
        f"{narrative.headline} {narrative.analysis_text}".count("지난 한 주") == 1
    )
    assert len(narrative.observations) == 3
    assert narrative.suggestions == ["기기 전원이 연결되어 있는지 확인해 주세요"]
    assert narrative.headline == (
        "지난 한 주 대상님의 생활은 확인된 자료 범위 안에서 "
        "세심하게 살펴보았습니다."
    )


def test_zero_only_night_awake_data_is_not_described_as_stable_sleep() -> None:
    metrics = _metrics()
    metrics = metrics.model_copy(
        update={
            "current": metrics.current.model_copy(
                update={
                    "sleep_time_avg": None,
                    "wake_up_time_avg": None,
                    "night_awake_count_avg": 0.0,
                }
            ),
            "previous": metrics.previous.model_copy(
                update={
                    "sleep_time_avg": None,
                    "wake_up_time_avg": None,
                    "night_awake_count_avg": 0.0,
                }
            ),
            "delta": metrics.delta.model_copy(
                update={
                    "sleep_time_minutes": None,
                    "wake_up_time_minutes": None,
                    "night_awake_count_avg": 0.0,
                }
            ),
        }
    )
    facts = build_fact_package(metrics)
    outline = facts.summary_outline

    assert outline is not None
    assert outline.life == (
        "움직임과 리모컨 사용량은 2주 전과 비슷한 수준으로 확인되었습니다."
    )
    assert "수면" not in outline.headline
    assert "수면" not in outline.available_item_list
    assert "수면" not in outline.omitted_item_list
    assert "수면" not in facts.allowed_topics
    assert "자료 상태" not in facts.allowed_topics
    narrative = build_fallback(facts)
    assert "수면" not in narrative.analysis_text
    assert "자료" not in narrative.analysis_text
    assert "출동" not in narrative.analysis_text


def test_risk_summary_excludes_unevaluable_sleep_from_headline_and_life() -> None:
    metrics = _metrics(
        current_updates={
            "humidity_out_of_range_days": 4,
            "environment_out_of_range_days": 4,
            "low_humidity_days": 4,
        }
    )
    metrics = metrics.model_copy(
        update={
            "current": metrics.current.model_copy(
                update={
                    "sleep_time_avg": None,
                    "wake_up_time_avg": None,
                    "night_awake_count_avg": 0.0,
                }
            ),
            "previous": metrics.previous.model_copy(
                update={
                    "sleep_time_avg": None,
                    "wake_up_time_avg": None,
                    "night_awake_count_avg": 0.0,
                }
            ),
            "delta": metrics.delta.model_copy(
                update={
                    "sleep_time_minutes": None,
                    "wake_up_time_minutes": None,
                    "night_awake_count_avg": 0.0,
                }
            ),
        }
    )
    facts = build_fact_package(metrics)
    outline = facts.summary_outline

    assert outline is not None
    assert outline.mode == "RISK"
    assert outline.issue_topic_list == ["환경"]
    assert (
        outline.headline
        == "지난 한 주 대상님의 실내 환경에서 세심한 확인이 필요한 변화가 나타났습니다."
    )
    assert outline.life == (
        "움직임과 리모컨 사용량은 2주 전과 비슷한 수준으로 확인되었습니다."
    )
    narrative = build_fallback(facts)
    assert "수면" not in narrative.headline
    assert "수면" not in narrative.analysis_text
    assert "자료" not in narrative.analysis_text
    assert "출동" not in narrative.analysis_text


@pytest.mark.parametrize(
    ("current_updates", "quality_code", "cause", "count_text"),
    [
        (
            {"device_good_count": 5, "device_power_count": 2},
            "PARTIAL_POWER",
            "기기 전원 확인",
            "2회",
        ),
        (
            {"device_good_count": 5, "device_position_count": 2},
            "PARTIAL_POSITION",
            "기기 위치 확인",
            "2회",
        ),
    ],
)
def test_partial_device_mode_explains_cause_and_significant_count(
    current_updates: dict[str, int],
    quality_code: str,
    cause: str,
    count_text: str,
) -> None:
    outline = build_weekly_summary_outline(_metrics(current_updates=current_updates))

    assert outline.mode == "PARTIAL_DEVICE"
    assert outline.data_quality_code == quality_code
    assert cause in outline.headline
    assert count_text in outline.safety
    assert "출동" not in outline.safety


def test_mixed_and_risk_modes_follow_verified_area_statuses() -> None:
    mixed = build_weekly_summary_outline(
        _metrics(
            current_updates={
                "temperature_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
            }
        )
    )
    risk = build_weekly_summary_outline(
        _metrics(
            current_updates={"movement_count_total": 39},
            previous_updates={"movement_count_total": 100},
        )
    )

    assert mixed.mode == "MIXED"
    assert "환경" in mixed.issue_topic_list
    assert "안정적이었지만" in mixed.headline
    assert risk.mode == "RISK"
    assert "활동" in risk.issue_topic_list
    assert "세심한 확인" in risk.headline
    assert "빠른" not in risk.headline
    assert "크게 줄었습니다" in risk.life


def test_validator_allows_only_significant_numbers_from_outline() -> None:
    facts = build_fact_package(_metrics(current_updates={"covered_days": 3}))
    narrative = build_fallback(facts)
    allowed_numbers = {"3"}

    validate_narrative(
        narrative,
        facts.allowed_topics,
        facts.required_topics,
        allowed_numbers,
        True,
    )
    invented = narrative.model_copy(
        update={
            "analysis_text": f"{narrative.analysis_text[:-1]} 9회."
        }
    )
    with pytest.raises(ValueError, match="unsupported digits"):
        validate_narrative(
            invented,
            facts.allowed_topics,
            facts.required_topics,
            allowed_numbers,
            True,
        )


def test_structured_summary_allows_one_selected_valuable_insight() -> None:
    facts = build_fact_package(_metrics())
    narrative = build_fallback(facts)
    selected = WeeklyNarrative(
        headline=narrative.headline,
        analysis_text="구체적으로 움직임과 리모컨 사용량은 2주 전과 비슷한 수준으로 확인되었습니다.",
        observations=["움직임과 리모컨 사용량은 2주 전과 비슷한 수준으로 확인되었습니다."],
        suggestions=narrative.suggestions,
    )
    assert (
        validate_narrative(
            selected,
            facts.allowed_topics,
            facts.required_topics,
            set(),
            True,
            facts.summary_outline.available_item_list,
        )
        == selected
    )


@pytest.mark.parametrize("legacy_phrase", ["이번 주", "지난주", "지난 주"])
def test_validator_rejects_legacy_report_period_phrases(
    legacy_phrase: str,
) -> None:
    facts = build_fact_package(_metrics())
    narrative = build_fallback(facts).model_copy(
        update={"headline": f"{legacy_phrase} 생활 흐름은 안정적이었습니다."}
    )

    with pytest.raises(ValueError, match="legacy report-period phrase"):
        validate_narrative(
            narrative,
            facts.allowed_topics,
            facts.required_topics,
            set(),
            True,
            facts.summary_outline.available_item_list,
        )

def test_structured_summary_requires_material_issue_but_not_stable_topics() -> None:
    facts = build_fact_package(
        _metrics(
            current_updates={
                "temperature_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
            }
        )
    )
    assert facts.required_topics == ["실내 환경"]
    selected = WeeklyNarrative(
        headline="지난 한 주 대상님의 실내 환경은 확인이 필요합니다.",
        analysis_text=(
            "구체적으로 실내 온도와 습도를 함께 살펴본 결과, 냉난방 상태를 확인할 필요가 있습니다."
        ),
        observations=["실내 온도와 습도에 확인이 필요한 변화가 나타났습니다."],
        suggestions=[],
    )

    assert (
        validate_narrative(
            selected,
            facts.allowed_topics,
            facts.required_topics,
            set(),
            True,
            facts.summary_outline.available_item_list,
        )
        == selected
    )
    assert "움직임" not in selected.analysis_text
    assert "기기" not in selected.analysis_text


@pytest.mark.parametrize("excluded_text", ["수면 흐름은 안정적이었습니다.", "출동 요청은 없었습니다."])
def test_structured_outline_rejects_report_excluded_topics(
    excluded_text: str,
) -> None:
    facts = build_fact_package(_metrics())
    narrative = build_fallback(facts).model_copy(
        update={"observations": [excluded_text]}
    )

    with pytest.raises(ValueError, match="report-excluded topic"):
        validate_narrative(
            narrative,
            facts.allowed_topics,
            facts.required_topics,
            set(),
            True,
            facts.summary_outline.available_item_list,
        )


def test_structured_outline_rejects_three_identical_sentence_endings() -> None:
    facts = build_fact_package(_metrics())
    narrative = build_fallback(facts).model_copy(
        update={
            "headline": "지난 한 주 생활 흐름을 확인했습니다.",
            "analysis_text": (
                "구체적으로 움직임과 리모컨 사용을 확인했습니다. "
                "이와 함께 실내 온도와 습도를 확인했습니다. "
                "또한 기기 데이터를 확인했습니다."
            ),
        }
    )

    with pytest.raises(ValueError, match="sentence ending"):
        validate_narrative(
            narrative,
            facts.allowed_topics,
            facts.required_topics,
            set(),
            True,
        )


def test_structured_summary_rejects_disconnected_or_urgent_sentences() -> None:
    facts = build_fact_package(_metrics())
    narrative = build_fallback(facts)
    disconnected = narrative.model_copy(
        update={
            "analysis_text": (
                "움직임과 리모컨 사용량은 2주 전과 비슷하게 유지되었습니다. "
                "실내 온도와 습도도 대체로 쾌적한 범위를 유지했습니다."
            )
        }
    )
    urgent = narrative.model_copy(
        update={"headline": "지난 한 주 생활 흐름은 빠른 확인이 필요했습니다."}
    )
    repeated_period = narrative.model_copy(
        update={
            "analysis_text": (
                "구체적으로 지난 한 주 움직임과 리모컨 사용량은 "
                "2주 전과 비슷한 수준으로 확인되었습니다."
            )
        }
    )

    with pytest.raises(ValueError, match="must use connectors"):
        validate_narrative(
            disconnected,
            facts.allowed_topics,
            facts.required_topics,
            set(),
            True,
            facts.summary_outline.available_item_list,
        )
    with pytest.raises(ValueError, match="urgent wording"):
        validate_narrative(
            urgent,
            facts.allowed_topics,
            facts.required_topics,
            set(),
            True,
            facts.summary_outline.available_item_list,
        )
    with pytest.raises(ValueError, match="repeats the report period"):
        validate_narrative(
            repeated_period,
            facts.allowed_topics,
            facts.required_topics,
            set(),
            True,
            facts.summary_outline.available_item_list,
        )
