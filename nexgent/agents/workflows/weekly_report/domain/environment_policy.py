"""Versioned product policy for interpreting weekly environment maxima."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from ax_contracts import WardWeeklyMetrics

EnvironmentStatus = Literal["unavailable", "good", "caution", "risk"]

HUMIDITY_RANGE = (40.0, 60.0)
HUMIDITY_CAUTION_RANGE = (30.0, 70.0)
TEMPERATURE_CAUTION_RANGE = (15.0, 30.0)
TEMPERATURE_RANGES = {
    1: (18.0, 20.0),
    2: (18.0, 20.0),
    3: (18.0, 20.0),
    4: (20.0, 22.0),
    5: (20.0, 22.0),
    6: (26.0, 28.0),
    7: (26.0, 28.0),
    8: (26.0, 28.0),
    9: (26.0, 28.0),
    10: (20.0, 22.0),
    11: (18.0, 20.0),
    12: (18.0, 20.0),
}


@dataclass(frozen=True, slots=True)
class EnvironmentAssessment:
    temperature_low: float
    temperature_high: float
    humidity_low: float
    humidity_high: float
    temperature_max: float | None
    humidity_max: float | None
    temperature_status: EnvironmentStatus
    humidity_status: EnvironmentStatus
    overall_status: EnvironmentStatus


def assess_environment(metrics: WardWeeklyMetrics) -> EnvironmentAssessment:
    """Assess weekly maxima using the reporting week's starting month."""

    temperature_low, temperature_high = TEMPERATURE_RANGES[metrics.week_start.month]
    humidity_low, humidity_high = HUMIDITY_RANGE
    current = metrics.current
    temperature_status = _classify(
        current.temperature_max,
        recommended_low=temperature_low,
        recommended_high=temperature_high,
        caution_low=TEMPERATURE_CAUTION_RANGE[0],
        caution_high=TEMPERATURE_CAUTION_RANGE[1],
    )
    humidity_status = _classify(
        current.humidity_max,
        recommended_low=humidity_low,
        recommended_high=humidity_high,
        caution_low=HUMIDITY_CAUTION_RANGE[0],
        caution_high=HUMIDITY_CAUTION_RANGE[1],
    )
    return EnvironmentAssessment(
        temperature_low=temperature_low,
        temperature_high=temperature_high,
        humidity_low=humidity_low,
        humidity_high=humidity_high,
        temperature_max=current.temperature_max,
        humidity_max=current.humidity_max,
        temperature_status=temperature_status,
        humidity_status=humidity_status,
        overall_status=_overall_status(temperature_status, humidity_status),
    )


def _classify(
    maximum: float | None,
    *,
    recommended_low: float,
    recommended_high: float,
    caution_low: float,
    caution_high: float,
) -> EnvironmentStatus:
    if maximum is None or not isfinite(maximum):
        return "unavailable"
    if maximum < caution_low or maximum > caution_high:
        return "risk"
    if recommended_low <= maximum <= recommended_high:
        return "good"
    return "caution"


def _overall_status(
    temperature: EnvironmentStatus,
    humidity: EnvironmentStatus,
) -> EnvironmentStatus:
    available = {temperature, humidity} - {"unavailable"}
    if not available:
        return "unavailable"
    if "risk" in available:
        return "risk"
    if "caution" in available:
        return "caution"
    return "good"
