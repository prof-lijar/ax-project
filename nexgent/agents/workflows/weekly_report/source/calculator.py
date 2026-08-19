"""Pure calculations matching the legacy ward-period service semantics."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, time, timedelta
from typing import Any

from ax_contracts import (
    WardWeeklyMetricDelta,
    WardWeeklyMetrics,
    WardWeeklyMetricSnapshot,
)


def calculate_metrics(
    *,
    ward_names: dict[int, str],
    week_start: date,
    daily_rows: list[dict[str, Any]],
    risk_rows: list[dict[str, Any]],
    dispatch_rows: list[dict[str, Any]],
) -> list[WardWeeklyMetrics]:
    by_period: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        index = 0 if row["date"] < week_start else 1
        by_period[(int(row["ward_id"]), index)].append(row)

    risk = {
        (int(row["ward_id"]), int(row["period_index"])): row for row in risk_rows
    }
    dispatch = {
        (int(row["ward_id"]), int(row["period_index"])): row
        for row in dispatch_rows
    }
    output = []
    for ward_id in sorted(ward_names):
        previous = _snapshot(
            by_period[(ward_id, 0)], risk.get((ward_id, 0)), dispatch.get((ward_id, 0))
        )
        current = _snapshot(
            by_period[(ward_id, 1)], risk.get((ward_id, 1)), dispatch.get((ward_id, 1))
        )
        output.append(
            WardWeeklyMetrics(
                ward_id=ward_id,
                display_name=ward_names[ward_id],
                week_start=week_start,
                week_end=week_start + timedelta(days=7),
                current=current,
                previous=previous,
                delta=_delta(current, previous),
            )
        )
    return output


def _snapshot(
    rows: list[dict[str, Any]],
    risk: dict[str, Any] | None,
    dispatch: dict[str, Any] | None,
) -> WardWeeklyMetricSnapshot:
    risk = risk or {}
    dispatch = dispatch or {}
    return WardWeeklyMetricSnapshot(
        covered_days=len({row["date"] for row in rows}),
        daily_summary_count=len(rows),
        device_count=len({row["device_id"] for row in rows if row["device_id"] is not None}),
        temperature_avg=_weighted_average(rows, "temperature", "temperature_count"),
        temperature_min=_minimum(rows, "min_temperature"),
        temperature_max=_maximum(rows, "max_temperature"),
        temperature_count=_sum(rows, "temperature_count"),
        humidity_avg=_weighted_average(rows, "humidity", "humidity_count"),
        humidity_min=_minimum(rows, "min_humidity"),
        humidity_max=_maximum(rows, "max_humidity"),
        humidity_count=_sum(rows, "humidity_count"),
        light_avg=_weighted_average(rows, "light", "light_count"),
        light_min=_minimum(rows, "min_light"),
        light_max=_maximum(rows, "max_light"),
        light_count=_sum(rows, "light_count"),
        light_on_time_minutes_avg=_average(rows, "light_on_time_minutes"),
        movement_count_avg=_average(rows, "movement_count"),
        remote_control_count_avg=_average(rows, "remote_control_count"),
        wake_up_time_avg=_average_time(rows, "wake_up_time"),
        sleep_time_avg=_average_time(rows, "sleep_time"),
        night_awake_count_avg=_average(rows, "night_awake_count"),
        risk_detected_count=int(risk.get("risk_detected_count") or 0),
        risk_resolved_count=int(risk.get("risk_resolved_count") or 0),
        risk_score_avg=_float_or_none(risk.get("risk_score_avg")),
        danger_days=int(risk.get("danger_days") or 0),
        dispatch_request_count=int(dispatch.get("dispatch_request_count") or 0),
        unresolved_dispatch_count=int(dispatch.get("unresolved_dispatch_count") or 0),
    )


def _delta(
    current: WardWeeklyMetricSnapshot, previous: WardWeeklyMetricSnapshot
) -> WardWeeklyMetricDelta:
    return WardWeeklyMetricDelta(
        covered_days=current.covered_days - previous.covered_days,
        temperature_avg=_difference(current.temperature_avg, previous.temperature_avg),
        humidity_avg=_difference(current.humidity_avg, previous.humidity_avg),
        light_avg=_difference(current.light_avg, previous.light_avg),
        light_on_time_minutes_avg=_difference(
            current.light_on_time_minutes_avg, previous.light_on_time_minutes_avg
        ),
        movement_count_avg=_difference(
            current.movement_count_avg, previous.movement_count_avg
        ),
        remote_control_count_avg=_difference(
            current.remote_control_count_avg, previous.remote_control_count_avg
        ),
        wake_up_time_minutes=_time_difference(
            current.wake_up_time_avg, previous.wake_up_time_avg
        ),
        sleep_time_minutes=_time_difference(
            current.sleep_time_avg, previous.sleep_time_avg
        ),
        night_awake_count_avg=_difference(
            current.night_awake_count_avg, previous.night_awake_count_avg
        ),
        risk_detected_count=current.risk_detected_count - previous.risk_detected_count,
        risk_resolved_count=current.risk_resolved_count - previous.risk_resolved_count,
        risk_score_avg=_difference(current.risk_score_avg, previous.risk_score_avg),
        danger_days=current.danger_days - previous.danger_days,
        dispatch_request_count=(
            current.dispatch_request_count - previous.dispatch_request_count
        ),
        unresolved_dispatch_count=(
            current.unresolved_dispatch_count - previous.unresolved_dispatch_count
        ),
    )


def _weighted_average(rows: list[dict[str, Any]], value: str, count: str) -> float | None:
    numerator = 0.0
    denominator = 0
    for row in rows:
        row_value = row[value]
        row_count = row[count] or 0
        if row_value is None or row_count == 0:
            continue
        numerator += float(row_value) * int(row_count)
        denominator += int(row_count)
    return numerator / denominator if denominator else None


def _average(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row[field] is not None]
    return sum(values) / len(values) if values else None


def _average_time(rows: list[dict[str, Any]], field: str) -> time | None:
    values = [row[field] for row in rows if row[field] is not None]
    if not values:
        return None
    seconds = int(
        sum(value.hour * 3600 + value.minute * 60 + value.second for value in values)
        / len(values)
    )
    return time(seconds // 3600, (seconds % 3600) // 60, seconds % 60)


def _sum(rows: list[dict[str, Any]], field: str) -> int:
    return sum(int(row[field] or 0) for row in rows)


def _minimum(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row[field] is not None]
    return min(values) if values else None


def _maximum(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row[field] is not None]
    return max(values) if values else None


def _difference(current: float | None, previous: float | None) -> float | None:
    return current - previous if current is not None and previous is not None else None


def _time_difference(current: time | None, previous: time | None) -> float | None:
    if current is None or previous is None:
        return None
    current_seconds = current.hour * 3600 + current.minute * 60 + current.second
    previous_seconds = previous.hour * 3600 + previous.minute * 60 + previous.second
    return (current_seconds - previous_seconds) / 60


def _float_or_none(value: Any) -> float | None:
    return float(value) if value is not None else None
