from datetime import date

import pytest
from ax_contracts import WardWeeklyMetrics

from workflows.weekly_report.domain.activity_policy import (
    ActivityMetric,
    activity_description,
    activity_summary,
    assess_activity,
)
from workflows.weekly_report.domain.derived_metrics import build_fact_package
from workflows.weekly_report.tools.source_repository import _mock_delta, _snapshot


def _metrics(
    *,
    movement_current: float | None = 100,
    movement_previous: float | None = 100,
    remote_current: float | None = 100,
    remote_previous: float | None = 100,
) -> WardWeeklyMetrics:
    current = _snapshot(101, current=True).model_copy(
        update={
            "movement_count_total": movement_current,
            "remote_control_count_total": remote_current,
        }
    )
    previous = _snapshot(101, current=False).model_copy(
        update={
            "movement_count_total": movement_previous,
            "remote_control_count_total": remote_previous,
        }
    )
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
    ("ratio", "status", "trend", "description", "summary"),
    [
        (
            39.9,
            "RISK",
            "decrease",
            "활동이 많이 줄었어요. 안부를 한 번 확인해 주세요.",
            "많이 감소",
        ),
        (40, "CAUTION", "decrease", "활동이 조금 줄어든 모습이에요.", "조금 감소"),
        (
            69.9,
            "CAUTION",
            "decrease",
            "활동이 조금 줄어든 모습이에요.",
            "조금 감소",
        ),
        (70, "GOOD", "stable", "활동은 비슷한 수준으로 이어졌어요.", "평소 수준"),
        (
            149.9,
            "GOOD",
            "stable",
            "활동은 비슷한 수준으로 이어졌어요.",
            "평소 수준",
        ),
        (150, "CAUTION", "increase", "활동이 조금 늘어난 모습이에요.", "조금 증가"),
        (
            150.1,
            "CAUTION",
            "increase",
            "활동이 조금 늘어난 모습이에요.",
            "조금 증가",
        ),
        (250, "CAUTION", "increase", "활동이 조금 늘어난 모습이에요.", "조금 증가"),
        (
            250.1,
            "RISK",
            "increase",
            "활동이 많이 늘었어요. 생활에 달라진 점이 있는지 살펴봐 주세요.",
            "많이 증가",
        ),
    ],
)
def test_activity_policy_classifies_total_ratio_boundaries(
    ratio: float,
    status: str,
    trend: str,
    description: str,
    summary: str,
) -> None:
    assessment = assess_activity(
        _metrics(movement_current=ratio, movement_previous=100)
    ).movement

    assert assessment.ratio_percent == pytest.approx(ratio)
    assert assessment.status == status
    assert assessment.trend == trend
    assert activity_description("movement", assessment) == description
    assert activity_summary("movement", assessment) == summary


@pytest.mark.parametrize(
    ("metric", "ratio", "status", "description", "summary"),
    [
        (
            "movement",
            100,
            "GOOD",
            "활동은 비슷한 수준으로 이어졌어요.",
            "평소 수준",
        ),
        (
            "remote_control",
            100,
            "GOOD",
            "TV 이용 등 일상적인 생활 패턴도 비슷하게 이어졌어요.",
            "평소 수준",
        ),
        (
            "movement",
            50,
            "CAUTION",
            "활동이 조금 줄어든 모습이에요.",
            "조금 감소",
        ),
        (
            "movement",
            200,
            "CAUTION",
            "활동이 조금 늘어난 모습이에요.",
            "조금 증가",
        ),
        (
            "remote_control",
            50,
            "CAUTION",
            "TV 이용 등 일상적인 생활 패턴이 조금 줄었어요.",
            "조금 감소",
        ),
        (
            "remote_control",
            200,
            "CAUTION",
            "TV 이용 등 일상적인 생활 패턴이 조금 늘었어요.",
            "조금 증가",
        ),
        (
            "movement",
            30,
            "RISK",
            "활동이 많이 줄었어요. 안부를 한 번 확인해 주세요.",
            "많이 감소",
        ),
        (
            "movement",
            300,
            "RISK",
            "활동이 많이 늘었어요. 생활에 달라진 점이 있는지 살펴봐 주세요.",
            "많이 증가",
        ),
        (
            "remote_control",
            30,
            "RISK",
            "TV 이용 등 일상적인 생활 패턴이 많이 줄었어요. 안부를 한 번 확인해 주세요.",
            "많이 감소",
        ),
        (
            "remote_control",
            300,
            "RISK",
            "TV 이용 등 일상적인 생활 패턴이 많이 늘었어요. 최근 생활에 달라진 점이 있는지 살펴봐 주세요.",
            "많이 증가",
        ),
    ],
)
def test_activity_policy_uses_approved_copy(
    metric: ActivityMetric,
    ratio: float,
    status: str,
    description: str,
    summary: str,
) -> None:
    metrics = _metrics(
        movement_current=ratio,
        movement_previous=100,
        remote_current=ratio,
        remote_previous=100,
    )
    activity = assess_activity(metrics)
    assessment = activity.movement if metric == "movement" else activity.remote_control

    assert assessment.status == status
    assert activity_description(metric, assessment) == description
    assert activity_summary(metric, assessment) == summary


@pytest.mark.parametrize("previous", [None, 0])
def test_activity_policy_discloses_unavailable_comparison(
    previous: float | None,
) -> None:
    assessment = assess_activity(
        _metrics(movement_current=10, movement_previous=previous)
    ).movement

    assert assessment.status == "UNAVAILABLE"
    assert assessment.ratio_percent is None
    assert activity_description("movement", assessment) == (
        "2주 전과 비교할 수 있는 움직임 합계 자료가 부족해요."
    )


def test_activity_facts_use_total_ratio_policy() -> None:
    facts = build_fact_package(
        _metrics(
            movement_current=30,
            movement_previous=100,
            remote_current=200,
            remote_previous=100,
        )
    )

    assert facts.weekly_report_data is not None
    assert facts.weekly_report_data.living_activity.status == "RISK"
    assert facts.weekly_report_data.living_activity.summary == "많이 감소"
    assert facts.weekly_report_data.living_pattern.status == "CAUTION"
    assert facts.weekly_report_data.living_pattern.summary == "조금 증가"
    assert "활동" in facts.allowed_topics
