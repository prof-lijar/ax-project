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
                "활동 감소",
                "안부를 한 번 확인해 주세요",
                "활동이 많이 줄어든 모습이에요.",
                "안부 전화하기",
                "ACT_RISK_01",
            ),
        ),
        (
            {"movement_count_total": 200},
            {"movement_count_total": 100},
            (
                "guide_activity",
                "movement_count",
                "CAUTION",
                2,
                "활동 증가",
                "생활에 달라진 점이 있는지 살펴봐 주세요",
                "활동이 평소보다 많이 늘어난 모습이에요.",
                "생활 확인하기",
                "ACT_RISK_02",
            ),
        ),
        (
            {"remote_control_count_total": 39},
            {"remote_control_count_total": 100},
            (
                "guide_activity",
                "remote_control_count",
                "RISK",
                4,
                "생활 패턴 감소",
                "안부를 한 번 확인해 주세요",
                "TV 이용 등 일상적인 생활 패턴이 많이 줄었어요.",
                "안부 전화하기",
                "ACT_RISK_03",
            ),
        ),
        (
            {"remote_control_count_total": 200},
            {"remote_control_count_total": 100},
            (
                "guide_activity",
                "remote_control_count",
                "CAUTION",
                5,
                "생활 패턴 증가",
                "최근 생활에 달라진 점이 있는지 살펴봐 주세요",
                "TV 이용 등 일상적인 생활 패턴이 많이 늘었어요.",
                "생활 확인하기",
                "ACT_RISK_04",
            ),
        ),
        (
            {
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "low_humidity_days": 2,
            },
            {},
            (
                "guide_env",
                "environment",
                "CAUTION",
                4,
                "건조한 환경",
                "실내가 너무 건조하지 않은지 살펴봐 주세요",
                "집 안이 건조한 날이 있었어요.",
                "환경 확인하기",
                "ENV_CAUTION_04",
            ),
        ),
        (
            {
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "high_humidity_days": 2,
            },
            {},
            (
                "guide_env",
                "environment",
                "CAUTION",
                3,
                "습한 환경",
                "제습이나 환기가 필요한지 살펴봐 주세요",
                "집 안이 습한 날이 있었어요.",
                "환경 확인하기",
                "ENV_CAUTION_03",
            ),
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "high_temperature_days": 2,
            },
            {},
            (
                "guide_env",
                "environment",
                "CAUTION",
                1,
                "더운 환경",
                "냉방이나 환기 상태를 확인해 주세요",
                "집 안이 조금 더운 날이 있었어요.",
                "환경 확인하기",
                "ENV_CAUTION_01",
            ),
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "low_temperature_days": 2,
            },
            {},
            (
                "guide_env",
                "environment",
                "CAUTION",
                2,
                "추운 환경",
                "난방 상태를 확인해 주세요",
                "집 안이 조금 추운 날이 있었어요.",
                "환경 확인하기",
                "ENV_CAUTION_02",
            ),
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_temperature_days": 4,
                "high_humidity_days": 4,
            },
            {},
            (
                "guide_env",
                "environment",
                "RISK",
                5,
                "덥고 습한 환경",
                "냉방과 환기 상태를 함께 확인해 주세요",
                "덥고 습한 날이 여러 번 이어졌어요.",
                "환경 확인하기",
                "ENV_RISK_05",
            ),
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_temperature_days": 4,
                "low_humidity_days": 4,
            },
            {},
            (
                "guide_env",
                "environment",
                "RISK",
                6,
                "덥고 건조한 환경",
                "냉방 상태와 실내 습도를 함께 확인해 주세요",
                "덥고 건조한 날이 여러 번 이어졌어요.",
                "환경 확인하기",
                "ENV_RISK_06",
            ),
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "humidity_out_of_range_days": 0,
                "environment_out_of_range_days": 4,
                "low_temperature_days": 4,
                "humidity_at_or_above_70_days": 4,
            },
            {},
            (
                "guide_env",
                "environment",
                "RISK",
                7,
                "춥고 습한 환경",
                "난방과 환기 상태를 함께 확인해 주세요",
                "춥고 습한 날이 여러 번 이어졌어요.",
                "환경 확인하기",
                "ENV_RISK_07",
            ),
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "low_temperature_days": 4,
                "low_humidity_days": 4,
            },
            {},
            (
                "guide_env",
                "environment",
                "RISK",
                8,
                "춥고 건조한 환경",
                "난방 상태와 실내 습도를 함께 확인해 주세요",
                "춥고 건조한 날이 여러 번 이어졌어요.",
                "환경 확인하기",
                "ENV_RISK_08",
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
                "전원 확인",
                "기기 전원이 잘 연결되어 있는지 확인해 주세요",
                "생활 정보가 들어오지 않은 날이 있었어요.",
                "기기 확인하기",
                "DEV_POWER_01",
            ),
        ),
        (
            {
                "device_good_count": 5,
                "device_power_count": 0,
                "device_position_count": 2,
            },
            {},
            (
                "guide_device_pos",
                "device_data",
                "CAUTION",
                1,
                "위치 확인",
                "기기가 제자리에 있는지 확인해 주세요",
                "생활 정보가 평소보다 적게 들어온 날이 있었어요.",
                "기기 확인하기",
                "DEV_POS_01",
            ),
        ),
    ],
)
def test_guardian_guides_use_exact_approved_copy(
    current_updates: dict[str, int | float],
    previous_updates: dict[str, int | float],
    expected: tuple[str, str, str, int, str, str, str, str, str | None],
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
        guide.description,
        guide.tag,
        guide.template_id,
    ) == expected


def test_guardian_guides_are_priority_ordered_and_capped_at_three() -> None:
    guides = build_guardian_guides(
        _metrics(
            current_updates={
                "movement_count_total": 39,
                "remote_control_count_total": 200,
                "temperature_out_of_range_days": 4,
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_temperature_days": 4,
                "high_humidity_days": 4,
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
        "전원 확인",
        "활동 감소",
        "생활 패턴 증가",
    ]


@pytest.mark.parametrize(
    ("current_updates", "previous_updates", "excluded_source"),
    [
        (
            {"movement_count_total": 251},
            {"movement_count_total": 100},
            "movement_count",
        ),
        (
            {"remote_control_count_total": 251},
            {"remote_control_count_total": 100},
            "remote_control_count",
        ),
    ],
)
def test_increase_risk_does_not_select_a_caution_only_action(
    current_updates: dict[str, int],
    previous_updates: dict[str, int],
    excluded_source: str,
) -> None:
    guides = build_guardian_guides(
        _metrics(
            current_updates=current_updates,
            previous_updates=previous_updates,
        )
    )

    assert all(guide.source != excluded_source for guide in guides)


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
        guide.description,
        guide.tag,
        guide.template_id,
    ) == (
        "guide_stable",
        "overall",
        "GOOD",
        1,
        "상태 양호",
        "평소처럼 안부를 확인해 주세요",
        "평소와 비슷한 생활 흐름이 이어지고 있어요.",
        "안부 전화하기",
        None,
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

    assert "## 1. 평소처럼 안부를 확인해 주세요" in report.markdown
    assert "- 설명: 평소와 비슷한 생활 흐름이 이어지고 있어요." in (report.markdown)
    assert "- 태그: 안부 전화하기" in report.markdown
    assert "- template_id:" not in report.markdown
    assert "별도 행동 제안은 없어요" not in report.markdown


def test_report_renders_only_deterministic_guides_with_metadata() -> None:
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

    assert "이번 주에는" not in report.markdown
    assert "빠른" not in report.markdown
    assert "## 1. 안부를 한 번 확인해 주세요" in report.markdown
    assert "- 설명: 활동이 많이 줄어든 모습이에요." in report.markdown
    assert "- 태그: 안부 전화하기" in report.markdown
    assert "- template_id: ACT_RISK_01" in report.markdown
    assert "## 1. 활동 감소" not in report.markdown
    assert "- 권장 행동:" not in report.markdown
    assert "평소 생활 흐름을 살펴보셔도 좋아요" not in report.markdown

    facts = build_fact_package(metrics)
    assert facts.suggested_actions[0] == "안부를 한 번 확인해 주세요"
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
        "condition": "활동 감소",
        "title": "안부를 한 번 확인해 주세요",
        "description": "활동이 많이 줄어든 모습이에요.",
        "tag": "안부 전화하기",
        "template_id": "ACT_RISK_01",
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

    assert "## 1. 안부를 한 번 확인해 주세요" in report.markdown
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
            "daily_summary_count": 0,
            "device_count": 0,
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
    assert "- 설명: 지난 한 주 기기 데이터 수신이 확인되지 않았어요." in (
        report.markdown
    )
    assert "- 태그: 기기 확인하기" in report.markdown
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

    assert "## 1. 평소처럼 안부를 확인해 주세요" in report.markdown
    assert "## 2. 지난 한 주에는" not in report.markdown


def test_report_deduplicates_formalized_model_copy_of_guardian_action() -> None:
    metrics = _metrics(
        current_updates={"movement_count_total": 39},
        previous_updates={"movement_count_total": 100},
    )
    narrative = WeeklyNarrative(
        headline="움직임이 2주 전보다 크게 줄었습니다.",
        analysis_text="움직임이 많이 줄어 안부 확인이 필요합니다.",
        observations=["평소보다 활동이 많이 줄었습니다."],
        suggestions=["안부를 한 번 확인해 주세요."],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert report.markdown.count("## 1. 안부를 한 번 확인해 주세요") == 1
    assert "## 2. 안부를 한 번 확인해 주세요" not in report.markdown
