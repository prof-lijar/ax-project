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
    ("ratio", "status", "trend"),
    [
        (39.9, "RISK", "decrease"),
        (40, "CAUTION", "decrease"),
        (69.9, "CAUTION", "decrease"),
        (70, "GOOD", "stable"),
        (150, "GOOD", "stable"),
        (150.1, "CAUTION", "increase"),
        (250, "CAUTION", "increase"),
        (250.1, "RISK", "increase"),
    ],
)
def test_activity_policy_classifies_total_ratio_boundaries(
    ratio: float,
    status: str,
    trend: str,
) -> None:
    assessment = assess_activity(
        _metrics(movement_current=ratio, movement_previous=100)
    ).movement

    assert assessment.ratio_percent == pytest.approx(ratio)
    assert assessment.status == status
    assert assessment.trend == trend


@pytest.mark.parametrize(
    ("metric", "ratio", "status", "description", "summary"),
    [
        (
            "movement",
            100,
            "GOOD",
            "움직임이 2주 전과 비슷하게 유지됐어요.",
            "움직임 평소 수준",
        ),
        (
            "remote_control",
            100,
            "GOOD",
            "리모컨 사용이 2주 전과 비슷했어요.",
            "리모컨 안정",
        ),
        (
            "movement",
            50,
            "CAUTION",
            "움직임이 2주 전보다 줄어든 흐름이 보여요.",
            "움직임 줄어듦",
        ),
        (
            "movement",
            200,
            "CAUTION",
            "움직임이 2주 전보다 늘어난 흐름이 보여요.",
            "움직임 늘어남",
        ),
        (
            "remote_control",
            50,
            "CAUTION",
            "리모컨 사용이 2주 전보다 줄어든 흐름이 보여요.",
            "리모컨 사용 감소",
        ),
        (
            "remote_control",
            200,
            "CAUTION",
            "리모컨 사용이 2주 전보다 늘어난 흐름이 보여요.",
            "리모컨 사용 증가",
        ),
        (
            "movement",
            30,
            "RISK",
            "움직임이 많이 줄어 안부 확인이 필요해요.",
            "움직임 확인 필요",
        ),
        (
            "movement",
            300,
            "RISK",
            "움직임이 크게 늘어 생활 변화 확인이 필요해요.",
            "생활 변화 확인 필요",
        ),
        (
            "remote_control",
            30,
            "RISK",
            "리모컨 사용이 많이 줄어 생활 확인이 필요해요.",
            "생활 확인 필요",
        ),
        (
            "remote_control",
            300,
            "RISK",
            "리모컨 사용이 반복적으로 많아 안부 확인을 권장해요.",
            "반복 사용 확인",
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

    assert facts.summary_outline is not None
    assert facts.summary_outline.mode == "RISK"
    assert "리모컨 사용은 2주 전보다 늘어난 흐름" in facts.summary_outline.life
    assert "움직임은 2주 전보다 크게 줄었습니다" in facts.summary_outline.life
    assert facts.summary_outline.life.index("리모컨 사용") < facts.summary_outline.life.index(
        "움직임"
    )
    assert not any(
        character.isdigit()
        for fact in facts.facts
        for character in fact.replace("2주 전", "")
    )
    assert "활동" in facts.allowed_topics
