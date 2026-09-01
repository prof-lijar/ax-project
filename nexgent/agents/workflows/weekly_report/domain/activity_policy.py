"""Versioned product policy for weekly activity-total comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from typing import Literal

from ax_contracts import WardWeeklyMetrics

ActivityStatus = Literal["UNAVAILABLE", "GOOD", "CAUTION", "RISK"]
ActivityTrend = Literal["unavailable", "stable", "decrease", "increase"]
ActivityMetric = Literal["movement", "remote_control"]


@dataclass(frozen=True, slots=True)
class ActivityMetricAssessment:
    current_total: float | None
    previous_total: float | None
    ratio_percent: float | None
    status: ActivityStatus
    trend: ActivityTrend


@dataclass(frozen=True, slots=True)
class ActivityAssessment:
    movement: ActivityMetricAssessment
    remote_control: ActivityMetricAssessment


def assess_activity(metrics: WardWeeklyMetrics) -> ActivityAssessment:
    """Compare current and previous weekly totals for both activity signals."""

    return ActivityAssessment(
        movement=_classify(
            metrics.current.movement_count_total,
            metrics.previous.movement_count_total,
        ),
        remote_control=_classify(
            metrics.current.remote_control_count_total,
            metrics.previous.remote_control_count_total,
        ),
    )


def activity_status_label(assessment: ActivityMetricAssessment) -> str:
    """Return the report-facing status or the unavailable disclosure."""

    if assessment.status == "UNAVAILABLE":
        return "자료 없음"
    return assessment.status


def activity_description(
    metric: ActivityMetric,
    assessment: ActivityMetricAssessment,
) -> str:
    """Return the approved Korean guidance for one activity signal."""

    if assessment.trend == "unavailable":
        if metric == "movement":
            return "2주 전과 비교할 수 있는 움직임 합계 자료가 부족해요."
        return "2주 전과 비교할 수 있는 리모컨 사용 합계 자료가 부족해요."

    return {
        ("movement", "stable"): "활동은 비슷한 수준으로 이어졌어요.",
        (
            "movement",
            "decrease",
            "CAUTION",
        ): "활동이 조금 줄어든 모습이에요.",
        (
            "movement",
            "increase",
            "CAUTION",
        ): "활동이 조금 늘어난 모습이에요.",
        (
            "movement",
            "decrease",
            "RISK",
        ): "활동이 많이 줄었어요. 안부를 한 번 확인해 주세요.",
        (
            "movement",
            "increase",
            "RISK",
        ): "활동이 많이 늘었어요. 생활에 달라진 점이 있는지 살펴봐 주세요.",
        (
            "remote_control",
            "stable",
        ): "TV 이용 등 일상적인 생활 패턴도 비슷하게 이어졌어요.",
        (
            "remote_control",
            "decrease",
            "CAUTION",
        ): "TV 이용 등 일상적인 생활 패턴이 조금 줄었어요.",
        (
            "remote_control",
            "increase",
            "CAUTION",
        ): "TV 이용 등 일상적인 생활 패턴이 조금 늘었어요.",
        (
            "remote_control",
            "decrease",
            "RISK",
        ): "TV 이용 등 일상적인 생활 패턴이 많이 줄었어요. 안부를 한 번 확인해 주세요.",
        (
            "remote_control",
            "increase",
            "RISK",
        ): "TV 이용 등 일상적인 생활 패턴이 많이 늘었어요. 최근 생활에 달라진 점이 있는지 살펴봐 주세요.",
    }[_description_key(metric, assessment)]


def activity_summary(
    metric: ActivityMetric,
    assessment: ActivityMetricAssessment,
) -> str:
    """Return the approved short summary for one activity signal."""

    if assessment.trend == "unavailable":
        return "비교 자료 없음"
    return {
        ("movement", "stable"): "평소 수준",
        ("movement", "decrease", "CAUTION"): "조금 감소",
        ("movement", "increase", "CAUTION"): "조금 증가",
        ("movement", "decrease", "RISK"): "많이 감소",
        ("movement", "increase", "RISK"): "많이 증가",
        ("remote_control", "stable"): "평소 수준",
        ("remote_control", "decrease", "CAUTION"): "조금 감소",
        ("remote_control", "increase", "CAUTION"): "조금 증가",
        ("remote_control", "decrease", "RISK"): "많이 감소",
        ("remote_control", "increase", "RISK"): "많이 증가",
    }[_description_key(metric, assessment)]


def _classify(
    current_total: float | None,
    previous_total: float | None,
) -> ActivityMetricAssessment:
    if (
        current_total is None
        or previous_total is None
        or not isfinite(current_total)
        or not isfinite(previous_total)
        or current_total < 0
        or previous_total <= 0
    ):
        return ActivityMetricAssessment(
            current_total=current_total,
            previous_total=previous_total,
            ratio_percent=None,
            status="UNAVAILABLE",
            trend="unavailable",
        )

    ratio = Decimal(str(current_total)) * Decimal(100) / Decimal(str(previous_total))
    if ratio < 40:
        status: ActivityStatus = "RISK"
        trend: ActivityTrend = "decrease"
    elif ratio < 70:
        status = "CAUTION"
        trend = "decrease"
    elif ratio < 150:
        status = "GOOD"
        trend = "stable"
    elif ratio <= 250:
        status = "CAUTION"
        trend = "increase"
    else:
        status = "RISK"
        trend = "increase"
    return ActivityMetricAssessment(
        current_total=current_total,
        previous_total=previous_total,
        ratio_percent=float(ratio),
        status=status,
        trend=trend,
    )


def _description_key(
    metric: ActivityMetric,
    assessment: ActivityMetricAssessment,
) -> (
    tuple[ActivityMetric, ActivityTrend]
    | tuple[ActivityMetric, ActivityTrend, ActivityStatus]
):
    if assessment.trend == "stable":
        return metric, assessment.trend
    return metric, assessment.trend, assessment.status
