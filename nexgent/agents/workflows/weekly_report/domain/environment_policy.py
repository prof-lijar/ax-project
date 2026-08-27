"""Versioned product policy for weekly indoor-environment day counts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ax_contracts import WardWeeklyMetrics

EnvironmentStatus = Literal["UNAVAILABLE", "GOOD", "CAUTION", "RISK"]

TEMPERATURE_RANGE = (15.0, 31.0)
HUMIDITY_RANGE = (30.0, 70.0)
GOOD_MAX_DEPARTURE_DAYS = 1
CAUTION_MIN_DEPARTURE_DAYS = 2
CAUTION_COMBINED_MAX_DEPARTURE_DAYS = 3
RISK_REPEAT_DAYS = 4
RISK_LOW_HUMIDITY_MAX = 30.0
RISK_HIGH_HUMIDITY_MAX = 70.0
RISK_LOW_TEMPERATURE_MAX = 15.0
RISK_HIGH_TEMPERATURE_MAX = 31.0


@dataclass(frozen=True, slots=True)
class EnvironmentAssessment:
    temperature_low: float
    temperature_high: float
    humidity_low: float
    humidity_high: float
    observed_days: int | None
    temperature_out_of_range_days: int | None
    humidity_out_of_range_days: int | None
    environment_out_of_range_days: int | None
    status: EnvironmentStatus
    variant: int | None


def assess_environment(metrics: WardWeeklyMetrics) -> EnvironmentAssessment:
    """Classify daily extrema using the approved year-round strict ranges."""

    temperature_low, temperature_high = TEMPERATURE_RANGE
    humidity_low, humidity_high = HUMIDITY_RANGE
    current = metrics.current
    counts = (
        current.environment_observed_days,
        current.temperature_out_of_range_days,
        current.humidity_out_of_range_days,
        current.environment_out_of_range_days,
        current.low_temperature_days,
        current.high_temperature_days,
        current.low_humidity_days,
        current.high_humidity_days,
    )
    status: EnvironmentStatus
    variant: int | None
    if any(value is None for value in counts) or current.environment_observed_days == 0:
        status, variant = "UNAVAILABLE", None
    else:
        status, variant = _classify(
            temperature_days=current.temperature_out_of_range_days or 0,
            humidity_days=current.humidity_out_of_range_days or 0,
            environment_days=current.environment_out_of_range_days or 0,
            low_temperature_days=current.low_temperature_days or 0,
            high_temperature_days=current.high_temperature_days or 0,
            low_humidity_days=current.low_humidity_days or 0,
            high_humidity_days=current.high_humidity_days or 0,
        )
    return EnvironmentAssessment(
        temperature_low=temperature_low,
        temperature_high=temperature_high,
        humidity_low=humidity_low,
        humidity_high=humidity_high,
        observed_days=current.environment_observed_days,
        temperature_out_of_range_days=current.temperature_out_of_range_days,
        humidity_out_of_range_days=current.humidity_out_of_range_days,
        environment_out_of_range_days=current.environment_out_of_range_days,
        status=status,
        variant=variant,
    )


def environment_status_label(assessment: EnvironmentAssessment) -> str:
    return "자료 없음" if assessment.status == "UNAVAILABLE" else assessment.status


def environment_description(assessment: EnvironmentAssessment) -> str:
    if assessment.status == "UNAVAILABLE" or assessment.variant is None:
        return "지난 한 주 실내 온습도 상태를 판단할 자료가 부족해요."
    return _COPY[(assessment.status, assessment.variant)][0]


def environment_summary(assessment: EnvironmentAssessment) -> str:
    if assessment.status == "UNAVAILABLE" or assessment.variant is None:
        return "환경 자료 없음"
    return _COPY[(assessment.status, assessment.variant)][1]


def _classify(
    *,
    temperature_days: int,
    humidity_days: int,
    environment_days: int,
    low_temperature_days: int,
    high_temperature_days: int,
    low_humidity_days: int,
    high_humidity_days: int,
) -> tuple[EnvironmentStatus, int]:
    has_temperature_departure = temperature_days > 0
    has_humidity_departure = humidity_days > 0

    if (
        environment_days >= RISK_REPEAT_DAYS
        and has_temperature_departure
        and has_humidity_departure
    ):
        return "RISK", 5
    if low_humidity_days >= RISK_REPEAT_DAYS:
        return "RISK", 1
    if high_humidity_days >= RISK_REPEAT_DAYS:
        return "RISK", 2
    if low_temperature_days >= RISK_REPEAT_DAYS:
        return "RISK", 3
    if high_temperature_days >= RISK_REPEAT_DAYS:
        return "RISK", 4
    if (
        CAUTION_MIN_DEPARTURE_DAYS
        <= environment_days
        <= CAUTION_COMBINED_MAX_DEPARTURE_DAYS
        and has_temperature_departure
        and has_humidity_departure
    ):
        return "CAUTION", 3
    if humidity_days >= CAUTION_MIN_DEPARTURE_DAYS:
        return "CAUTION", 1
    if temperature_days >= CAUTION_MIN_DEPARTURE_DAYS:
        return "CAUTION", 2
    if environment_days == 0:
        return "GOOD", 1
    if environment_days <= GOOD_MAX_DEPARTURE_DAYS:
        return "GOOD", 2
    return "CAUTION", 3


_COPY: dict[tuple[EnvironmentStatus, int], tuple[str, str]] = {
    ("GOOD", 1): (
        "실내 온습도가 대체로 적정 범위에 있었어요.",
        "쾌적 유지",
    ),
    ("GOOD", 2): (
        "온도와 습도가 생활하기 좋은 범위에 가까웠어요.",
        "적정 범위",
    ),
    ("CAUTION", 1): (
        "실내 습도에 주의가 필요한 시간이 있었어요.",
        "습도 주의",
    ),
    ("CAUTION", 2): (
        "실내 온도가 평소보다 불편할 수 있는 구간에 있었어요.",
        "온도 주의",
    ),
    ("CAUTION", 3): (
        "온도나 습도 변화가 며칠간 이어져 확인이 필요해요.",
        "온습도 주의",
    ),
    ("RISK", 1): (
        "건조한 실내 환경이 반복됐어요.",
        "습도 확인 필요",
    ),
    ("RISK", 2): (
        "습한 실내 환경이 반복됐어요.",
        "습도 확인 필요",
    ),
    ("RISK", 3): (
        "추운 실내 환경이 반복됐어요.",
        "온도 확인 필요",
    ),
    ("RISK", 4): (
        "더운 실내 환경이 반복됐어요.",
        "온습도 확인 필요",
    ),
    ("RISK", 5): (
        "권장 온도와 습도 이탈이 여러 날 이어져 냉난방·환기 상태 확인이 필요해요.",
        "온습도 확인 필요",
    ),
}
