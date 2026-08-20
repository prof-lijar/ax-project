"""Versioned product policy for interpreting weekly environment extrema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ax_contracts import WardWeeklyMetrics

RangeStatus = Literal["unavailable", "normal", "low", "high", "variable"]

HUMIDITY_RANGE = (40.0, 60.0)
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
    temperature_status: RangeStatus
    humidity_status: RangeStatus


def assess_environment(metrics: WardWeeklyMetrics) -> EnvironmentAssessment:
    """Assess extrema using the reporting week's starting month."""

    temperature_low, temperature_high = TEMPERATURE_RANGES[metrics.week_start.month]
    humidity_low, humidity_high = HUMIDITY_RANGE
    current = metrics.current
    return EnvironmentAssessment(
        temperature_low=temperature_low,
        temperature_high=temperature_high,
        humidity_low=humidity_low,
        humidity_high=humidity_high,
        temperature_status=_classify(
            current.temperature_min,
            current.temperature_max,
            temperature_low,
            temperature_high,
        ),
        humidity_status=_classify(
            current.humidity_min,
            current.humidity_max,
            humidity_low,
            humidity_high,
        ),
    )


def _classify(
    minimum: float | None,
    maximum: float | None,
    low: float,
    high: float,
) -> RangeStatus:
    if minimum is None or maximum is None:
        return "unavailable"
    below = minimum is not None and minimum < low
    above = maximum is not None and maximum > high
    if below and above:
        return "variable"
    if below:
        return "low"
    if above:
        return "high"
    return "normal"
