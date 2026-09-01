"""Versioned product policy for weekly indoor-environment day counts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ax_contracts import WardWeeklyMetrics

EnvironmentStatus = Literal["UNAVAILABLE", "GOOD", "CAUTION", "RISK"]

TEMPERATURE_RANGE = (15.0, 31.0)
HUMIDITY_RANGE = (30.0, 70.0)
COOL_TEMPERATURE_THRESHOLD = 18.0
HUMIDITY_AT_OR_ABOVE_THRESHOLD = 70.0
CAUTION_MIN_DEPARTURE_DAYS = 2
CAUTION_COMBINED_MAX_DEPARTURE_DAYS = 3
RISK_REPEAT_DAYS = 4


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
    """Classify daily maxima using the approved inclusive year-round ranges."""

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
            environment_days=current.environment_out_of_range_days or 0,
            low_temperature_days=current.low_temperature_days or 0,
            cool_temperature_days=(
                current.cool_temperature_days
                if current.cool_temperature_days is not None
                else current.low_temperature_days or 0
            ),
            high_temperature_days=current.high_temperature_days or 0,
            low_humidity_days=current.low_humidity_days or 0,
            high_humidity_days=current.high_humidity_days or 0,
            humidity_at_or_above_70_days=(
                current.humidity_at_or_above_70_days
                if current.humidity_at_or_above_70_days is not None
                else current.high_humidity_days or 0
            ),
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
    environment_days: int,
    low_temperature_days: int,
    cool_temperature_days: int,
    high_temperature_days: int,
    low_humidity_days: int,
    high_humidity_days: int,
    humidity_at_or_above_70_days: int,
) -> tuple[EnvironmentStatus, int]:
    combined_risk = (
        (high_temperature_days, high_humidity_days, 5),
        (high_temperature_days, low_humidity_days, 6),
        (low_temperature_days, humidity_at_or_above_70_days, 7),
        (low_temperature_days, low_humidity_days, 8),
    )
    for temperature_count, humidity_count, variant in combined_risk:
        if temperature_count >= RISK_REPEAT_DAYS and humidity_count >= RISK_REPEAT_DAYS:
            return "RISK", variant
    directional = (
        (high_temperature_days, 1),
        (low_temperature_days, 2),
        (high_humidity_days, 3),
        (low_humidity_days, 4),
    )
    for days, variant in directional:
        if days >= RISK_REPEAT_DAYS:
            return "RISK", variant

    combined_caution = (
        (high_temperature_days, high_humidity_days, 5),
        (high_temperature_days, low_humidity_days, 6),
        (cool_temperature_days, high_humidity_days, 7),
        (low_temperature_days, low_humidity_days, 8),
    )
    for temperature_count, humidity_count, variant in combined_caution:
        if (
            CAUTION_MIN_DEPARTURE_DAYS
            <= temperature_count
            <= CAUTION_COMBINED_MAX_DEPARTURE_DAYS
            and CAUTION_MIN_DEPARTURE_DAYS
            <= humidity_count
            <= CAUTION_COMBINED_MAX_DEPARTURE_DAYS
        ):
            return "CAUTION", variant
    for days, variant in directional:
        if days >= CAUTION_MIN_DEPARTURE_DAYS:
            return "CAUTION", variant
    if environment_days <= 1:
        return "GOOD", 1

    # The sheet has no separate mixed-direction template. Select the most
    # frequent verified direction deterministically without escalating it to
    # RISK unless the same condition repeats on four or more dates.
    _, variant = max(directional, key=lambda item: (item[0], -item[1]))
    return "CAUTION", variant


_COPY: dict[tuple[EnvironmentStatus, int], tuple[str, str]] = {
    ("GOOD", 1): (
        "집 안 온도와 습도가 대체로 쾌적하게 유지됐어요.",
        "쾌적",
    ),
    ("CAUTION", 1): (
        "집 안이 조금 더운 날이 있었어요. 냉방이나 환기 상태를 한 번 살펴봐 주세요.",
        "조금 더움",
    ),
    ("CAUTION", 2): (
        "집 안이 조금 추운 날이 있었어요. 난방 상태를 한 번 확인해 주세요.",
        "조금 추움",
    ),
    ("CAUTION", 3): (
        "집 안이 습한 날이 있었어요. 제습이나 환기가 필요한지 살펴봐 주세요.",
        "습함",
    ),
    ("CAUTION", 4): (
        "집 안이 건조한 날이 있었어요. 너무 건조하지 않은지 한 번 살펴봐 주세요.",
        "건조함",
    ),
    ("CAUTION", 5): (
        "덥고 습한 날이 있었어요. 냉방과 환기가 잘 되고 있는지 함께 살펴봐 주세요.",
        "덥고 습함",
    ),
    ("CAUTION", 6): (
        "집 안이 덥고 건조한 날이 있었어요. 냉방 상태와 실내 습도를 함께 살펴봐 주세요.",
        "덥고 건조함",
    ),
    ("CAUTION", 7): (
        "집 안이 다소 서늘하고 습한 날이 있었어요. 난방과 환기 상태를 함께 살펴봐 주세요.",
        "서늘하고 습함",
    ),
    ("CAUTION", 8): (
        "집 안이 춥고 건조한 날이 있었어요. 난방 상태와 실내 습도를 함께 살펴봐 주세요.",
        "춥고 건조함",
    ),
    ("RISK", 1): (
        "집 안이 많이 더운 날이 여러 번 이어졌어요. 냉방이 잘 되고 있는지 조금 더 세심하게 살펴봐 주세요.",
        "더운 날 이어짐",
    ),
    ("RISK", 2): (
        "집 안이 추운 날이 여러 번 이어졌어요. 난방 상태와 생활에 불편함은 없는지 살펴봐 주세요.",
        "추운 날 이어짐",
    ),
    ("RISK", 3): (
        "습한 날이 여러 번 이어졌어요. 제습이나 환기가 잘 되고 있는지 살펴봐 주세요.",
        "습한 날 이어짐",
    ),
    ("RISK", 4): (
        "건조한 날이 여러 번 이어졌어요. 집 안이 너무 건조하지 않은지 살펴봐 주세요.",
        "건조한 날 이어짐",
    ),
    ("RISK", 5): (
        "덥고 습한 날이 여러 번 이어졌어요. 냉방과 환기가 잘 되고 있는지 조금 더 세심하게 살펴봐 주세요.",
        "덥고 습한 날 이어짐",
    ),
    ("RISK", 6): (
        "덥고 건조한 날이 여러 번 이어졌어요. 냉방 상태와 실내 습도를 함께 살펴봐 주세요.",
        "덥고 건조한 날 이어짐",
    ),
    ("RISK", 7): (
        "춥고 습한 날이 여러 번 이어졌어요. 난방과 환기 상태를 함께 살펴봐 주세요.",
        "춥고 습한 날 이어짐",
    ),
    ("RISK", 8): (
        "춥고 건조한 날이 여러 번 이어졌어요. 난방 상태와 실내 습도를 조금 더 세심하게 살펴봐 주세요.",
        "춥고 건조한 날 이어짐",
    ),
}
