"""Versioned product policy for weekly device reception status."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ax_contracts import WardWeeklyMetricSnapshot

DeviceReceptionStatus = Literal["UNAVAILABLE", "GOOD", "CAUTION"]
DeviceReceptionKind = Literal[
    "unavailable",
    "device_no_data",
    "device_good",
    "device_power",
    "device_position",
]


@dataclass(frozen=True, slots=True)
class DeviceReceptionAssessment:
    status: DeviceReceptionStatus
    kind: DeviceReceptionKind
    source_count: int
    good_count: int | None
    other_count: int | None
    power_count: int | None
    position_count: int | None


def assess_device_reception(
    snapshot: WardWeeklyMetricSnapshot,
) -> DeviceReceptionAssessment:
    """Apply power-first precedence to deterministic reception counts."""

    counts = (
        snapshot.device_good_count,
        snapshot.device_power_count,
        snapshot.device_position_count,
    )
    status: DeviceReceptionStatus
    kind: DeviceReceptionKind
    if snapshot.daily_summary_count == 0:
        status, kind = "UNAVAILABLE", "device_no_data"
    elif any(value is None for value in counts):
        status, kind = "UNAVAILABLE", "unavailable"
    elif (snapshot.device_power_count or 0) >= 2:
        status, kind = "CAUTION", "device_power"
    elif (snapshot.device_position_count or 0) >= 2:
        status, kind = "CAUTION", "device_position"
    elif (snapshot.device_good_count or 0) >= 1:
        status, kind = "GOOD", "device_good"
    else:
        status, kind = "UNAVAILABLE", "unavailable"
    classified_count = (
        None
        if any(value is None for value in counts)
        else sum(value or 0 for value in counts)
    )
    other_count = (
        None
        if classified_count is None
        else max(0, snapshot.daily_summary_count - classified_count)
    )
    return DeviceReceptionAssessment(
        status=status,
        kind=kind,
        source_count=snapshot.daily_summary_count,
        good_count=snapshot.device_good_count,
        other_count=other_count,
        power_count=snapshot.device_power_count,
        position_count=snapshot.device_position_count,
    )


def device_reception_status_label(assessment: DeviceReceptionAssessment) -> str:
    if assessment.kind == "device_no_data":
        return "자료 없음"
    if assessment.status == "UNAVAILABLE":
        return "판정 불가"
    return assessment.status


def device_reception_description(assessment: DeviceReceptionAssessment) -> str:
    return _COPY[assessment.kind][0]


def device_reception_summary(assessment: DeviceReceptionAssessment) -> str:
    return _COPY[assessment.kind][1]


_COPY: dict[DeviceReceptionKind, tuple[str, str]] = {
    "unavailable": (
        "지난 한 주 기기 상태를 판단할 자료가 충분하지 않아요.",
        "기기 상태 확인 필요",
    ),
    "device_no_data": (
        "기기 전원이 연결되어 있는지 확인해 주세요.",
        "기기 상태 확인 필요",
    ),
    "device_good": (
        "생활 정보가 빠짐없이 잘 들어왔어요.",
        "정상",
    ),
    "device_power": (
        "생활 정보가 들어오지 않은 날이 있었어요. 기기 전원이 잘 연결되어 있는지 확인해 주세요.",
        "전원 확인",
    ),
    "device_position": (
        "일부 생활 정보가 적게 들어온 날이 있었어요. 기기가 제자리에 있는지 확인해 주세요.",
        "위치 확인",
    ),
}
