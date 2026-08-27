from datetime import date

import pytest
from ax_contracts import (
    NarrativeGenerationMetadata,
    WardWeeklyMetrics,
    WeeklyNarrative,
)

from workflows.weekly_report.agents.reporter.fallback import build_fallback
from workflows.weekly_report.domain.derived_metrics import build_fact_package
from workflows.weekly_report.domain.guardian_guidance_policy import (
    build_guardian_guides,
)
from workflows.weekly_report.domain.rendering import render_report
from workflows.weekly_report.tools.source_repository import _mock_delta, _snapshot


def _metrics(
    *,
    current_updates: dict[str, int | float] | None = None,
    previous_updates: dict[str, int | float] | None = None,
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


@pytest.mark.parametrize(
    ("current_updates", "previous_updates", "expected"),
    [
        (
            {"movement_count_total": 39},
            {"movement_count_total": 100},
            (
                "guide_activity",
                "movement_count",
                "RISK",
                1,
                "움직임 감소",
                "안부 확인이 필요해요",
                "움직임이 많이 줄었어요.",
            ),
        ),
        (
            {"movement_count_total": 251},
            {"movement_count_total": 100},
            (
                "guide_activity",
                "movement_count",
                "RISK",
                2,
                "움직임 증가",
                "생활 변화를 확인해 주세요",
                "움직임이 평소보다 크게 늘었어요.",
            ),
        ),
        (
            {"remote_control_count_total": 39},
            {"remote_control_count_total": 100},
            (
                "guide_activity",
                "remote_control_count",
                "RISK",
                3,
                "리모컨 감소",
                "생활 확인이 필요해요",
                "리모컨 사용이 많이 줄었어요.",
            ),
        ),
        (
            {"remote_control_count_total": 251},
            {"remote_control_count_total": 100},
            (
                "guide_activity",
                "remote_control_count",
                "RISK",
                4,
                "리모컨 증가",
                "안부 전화를 권해요",
                "리모컨 사용이 반복적으로 많았어요.",
            ),
        ),
        (
            {
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "low_humidity_days": 4,
            },
            {},
            (
                "guide_env",
                "environment",
                "RISK",
                1,
                "습도 낮음",
                "실내가 건조해요",
                "실내가 많이 건조해 가습이나 환기 상태를 확인해 주세요.",
            ),
        ),
        (
            {
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_humidity_days": 4,
            },
            {},
            (
                "guide_env",
                "environment",
                "RISK",
                2,
                "습도 높음",
                "실내가 습해요",
                "실내가 많이 습해 곰팡이나 냄새가 생길 수 있어요.",
            ),
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_temperature_days": 4,
            },
            {},
            (
                "guide_env",
                "environment",
                "RISK",
                3,
                "온도 높음",
                "실내가 더워요",
                "실내 온도가 높아 냉방이나 환기 상태를 확인해 주세요.",
            ),
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "low_temperature_days": 4,
            },
            {},
            (
                "guide_env",
                "environment",
                "RISK",
                4,
                "온도 낮음",
                "실내가 추워요",
                "실내 온도가 낮아 난방 상태를 확인해 주세요.",
            ),
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 4,
            },
            {},
            (
                "guide_env",
                "environment",
                "RISK",
                5,
                "온도 및 습도 권장 범위 이탈 반복",
                "생활 환경을 확인해 주세요",
                "실내 온도와 습도가 권장 범위 이탈이 반복되었어요.",
            ),
        ),
        (
            {
                "device_good_count": 3,
                "device_power_count": 2,
                "device_position_count": 0,
            },
            {},
            (
                "guide_device_power",
                "device_data",
                "CAUTION",
                1,
                "전원뽑음 주의",
                "전원 확인이 필요해요",
                "기기 전원이 빠진 이력이 있어요.",
            ),
        ),
        (
            {
                "device_good_count": 7,
                "device_power_count": 0,
                "device_position_count": 2,
            },
            {},
            (
                "guide_device_pos",
                "device_data",
                "CAUTION",
                1,
                "기기위치변경 주의",
                "기기 위치 확인이 필요해요",
                "움직임·리모컨 사용이 적게 확인됐어요.",
            ),
        ),
    ],
)
def test_guardian_guides_use_exact_approved_copy(
    current_updates: dict[str, int | float],
    previous_updates: dict[str, int | float],
    expected: tuple[str, str, str, int, str, str, str],
) -> None:
    guides = build_guardian_guides(
        _metrics(
            current_updates=current_updates,
            previous_updates=previous_updates,
        )
    )

    assert len(guides) == 1
    guide = guides[0]
    assert (
        guide.guide_type,
        guide.source,
        guide.status,
        guide.variant,
        guide.condition_label,
        guide.title,
        guide.analysis,
    ) == expected


def test_guardian_guides_are_priority_ordered_and_capped_at_three() -> None:
    guides = build_guardian_guides(
        _metrics(
            current_updates={
                "movement_count_total": 39,
                "remote_control_count_total": 251,
                "temperature_out_of_range_days": 2,
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 4,
                "device_good_count": 3,
                "device_power_count": 2,
                "device_position_count": 0,
            },
            previous_updates={
                "movement_count_total": 100,
                "remote_control_count_total": 100,
            },
        )
    )

    assert [guide.condition_label for guide in guides] == [
        "움직임 감소",
        "리모컨 증가",
        "온도 및 습도 권장 범위 이탈 반복",
    ]


def test_all_good_report_gets_stable_guardian_guide() -> None:
    metrics = _metrics(current_updates={"risk_detected_count": 0})

    guides = build_guardian_guides(metrics)

    assert len(guides) == 1
    guide = guides[0]
    assert (
        guide.guide_type,
        guide.source,
        guide.status,
        guide.variant,
        guide.condition_label,
        guide.title,
        guide.analysis,
    ) == (
        "guide_stable",
        "overall",
        "GOOD",
        1,
        "상태 양호",
        "꾸준히 안부를 확인해 주세요",
        "지난 한 주는 큰 이상 없이 안정적인 흐름을 보였어요.",
    )


@pytest.mark.parametrize(
    "current_updates",
    [
        {"movement_count_total": 60, "risk_detected_count": 0},
        {"risk_score_avg": 70, "risk_detected_count": 0},
        {"risk_detected_count": 1},
    ],
)
def test_stable_guide_is_not_used_when_any_issue_exists(
    current_updates: dict[str, int | float],
) -> None:
    metrics = _metrics(
        current_updates=current_updates,
        previous_updates={"movement_count_total": 100},
    )

    guides = build_guardian_guides(metrics)

    assert not any(guide.guide_type == "guide_stable" for guide in guides)


def test_report_renders_stable_guide_when_no_issue_action_exists() -> None:
    metrics = _metrics(current_updates={"risk_detected_count": 0})
    narrative = WeeklyNarrative(
        headline="지난 한 주 생활 흐름이 안정적으로 유지되었습니다.",
        analysis_text="확인된 생활 흐름은 대체로 안정적이었습니다.",
        suggestions=[],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert "## 1. 꾸준히 안부를 확인해 주세요" in report.markdown
    assert "- 분석: 지난 한 주는 큰 이상 없이 안정적인 흐름을 보였어요." in (
        report.markdown
    )
    assert "별도 행동 제안은 없어요" not in report.markdown


def test_report_renders_deterministic_guide_before_model_suggestions() -> None:
    metrics = _metrics(
        current_updates={"movement_count_total": 39},
        previous_updates={"movement_count_total": 100},
    )
    narrative = WeeklyNarrative(
        headline="지난 한 주 생활 흐름을 살펴봤어요.",
        analysis_text=(
            "지난 한 주 생활 흐름을 차분히 살펴봤어요. "
            "확인된 변화는 평소 모습과 함께 살펴보면 좋아요. "
            "자료에서 확인된 내용만 정리했어요. "
            "가볍게 안부를 살펴보셔도 좋아요."
        ),
        observations=["생활 흐름을 확인했어요."],
        suggestions=["평소 생활 흐름을 살펴보셔도 좋아요."],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert (
        "이번 주에는 안부를 확인하고 실제 생활 상태를 함께 살펴봐 주세요."
        in report.markdown
    )
    assert "빠른" not in report.markdown
    assert "## 1. 안부 확인이 필요해요" in report.markdown
    assert "- 분석: 움직임이 많이 줄었어요." in report.markdown
    assert "## 1. 움직임 감소" not in report.markdown
    assert "- 권장 행동:" not in report.markdown
    assert "## 2. 평소 생활 흐름을 살펴보셔도 좋아요" in report.markdown

    facts = build_fact_package(metrics)
    assert facts.suggested_actions[0] == "안부 확인이 필요해요"
    assert [item.source for item in facts.section_assessments] == [
        "movement_count",
        "remote_control_count",
        "temperature",
        "humidity",
        "device_data",
    ]
    assert facts.guardian_action_candidates[0].model_dump() == {
        "source": "movement_count",
        "status": "RISK",
        "condition": "움직임 감소",
        "title": "안부 확인이 필요해요",
        "analysis": "움직임이 많이 줄었어요.",
    }


def test_report_keeps_deterministic_guide_when_model_suggestions_are_empty() -> None:
    metrics = _metrics(
        current_updates={"movement_count_total": 39},
        previous_updates={"movement_count_total": 100},
    )
    narrative = WeeklyNarrative(
        headline="지난 한 주 움직임 흐름을 살펴봤어요.",
        analysis_text="움직임이 많이 줄어 안부 확인이 필요해요.",
        observations=["움직임이 많이 줄었어요."],
        suggestions=[],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert "## 1. 안부 확인이 필요해요" in report.markdown
    assert "별도 행동 제안은 없어요" not in report.markdown


def test_no_sensor_data_gets_power_check_guide_without_generic_action() -> None:
    base = _metrics()
    current = base.current.model_copy(
        update={
            "covered_days": 0,
            "movement_count_total": None,
            "remote_control_count_total": None,
            "temperature_out_of_range_days": None,
            "humidity_out_of_range_days": None,
            "environment_out_of_range_days": None,
            "device_good_count": None,
            "device_power_count": None,
            "device_position_count": None,
        }
    )
    previous = base.previous.model_copy(
        update={
            "movement_count_total": None,
            "remote_control_count_total": None,
        }
    )
    metrics = base.model_copy(
        update={
            "current": current,
            "previous": previous,
            "delta": _mock_delta(current, previous),
        }
    )
    facts = build_fact_package(metrics)
    narrative = build_fallback(facts)

    report = render_report(
        metrics,
        narrative,
        "template_fallback",
        NarrativeGenerationMetadata(
            prompt_version="test",
            validation_status="fallback",
        ),
    )

    assert "## 1. 기기 전원이 연결되어 있는지 확인해 주세요" in report.markdown
    assert "- 분석: 지난 한 주 기기 데이터 수신이 확인되지 않았어요." in report.markdown
    assert "지난 한 주에는 안부를 확인하며" not in report.markdown


def test_report_does_not_render_summary_close_as_numbered_guardian_action() -> None:
    metrics = _metrics(current_updates={"risk_detected_count": 0})
    narrative = WeeklyNarrative(
        headline="지난 한 주 생활 흐름이 안정적으로 유지되었습니다.",
        analysis_text="확인된 생활 흐름은 대체로 안정적이었습니다.",
        observations=["생활 흐름이 안정적으로 유지되었습니다."],
        suggestions=[
            "지난 한 주에는 안부를 확인하며, 확인된 생활 흐름을 함께 살펴봐 주세요"
        ],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert "## 1. 꾸준히 안부를 확인해 주세요" in report.markdown
    assert "## 2. 지난 한 주에는" not in report.markdown


def test_report_deduplicates_formalized_model_copy_of_guardian_action() -> None:
    metrics = _metrics(
        current_updates={"movement_count_total": 39},
        previous_updates={"movement_count_total": 100},
    )
    narrative = WeeklyNarrative(
        headline="움직임이 2주 전보다 크게 줄었습니다.",
        analysis_text="움직임이 많이 줄어 안부 확인이 필요합니다.",
        observations=["움직임이 많이 줄었습니다."],
        suggestions=["안부 확인이 필요합니다."],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert report.markdown.count("## 1. 안부 확인이 필요해요") == 1
    assert "## 2. 안부 확인이 필요합니다" not in report.markdown
