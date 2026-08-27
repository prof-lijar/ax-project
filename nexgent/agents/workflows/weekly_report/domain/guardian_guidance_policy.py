"""Deterministic guardian action guides selected from verified report statuses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ax_contracts import WardWeeklyMetrics

from .activity_policy import assess_activity
from .device_reception_policy import assess_device_reception
from .environment_policy import assess_environment
from .risk_score_policy import assess_risk_score

GuideType = Literal[
    "guide_activity",
    "guide_env",
    "guide_device_power",
    "guide_device_pos",
    "guide_device_no_data",
    "guide_stable",
]
GuideStatus = Literal["GOOD", "RISK", "CAUTION"]


@dataclass(frozen=True, slots=True)
class GuardianGuide:
    guide_type: GuideType
    source: str
    status: GuideStatus
    variant: int
    condition_label: str
    title: str
    analysis: str


def build_guardian_guides(metrics: WardWeeklyMetrics) -> list[GuardianGuide]:
    """Return at most three approved guides in product-priority order."""

    guides: list[GuardianGuide] = []
    reception = assess_device_reception(metrics.current)
    if reception.kind == "device_no_data":
        guides.append(_GUIDES[("guide_device_no_data", "device_data", 1)])

    activity = assess_activity(metrics)
    if activity.movement.status == "RISK":
        variant = 1 if activity.movement.trend == "decrease" else 2
        guides.append(_GUIDES[("guide_activity", "movement_count", variant)])
    if activity.remote_control.status == "RISK":
        variant = 3 if activity.remote_control.trend == "decrease" else 4
        guides.append(_GUIDES[("guide_activity", "remote_control_count", variant)])

    environment = assess_environment(metrics)
    if environment.status == "RISK" and environment.variant is not None:
        semantic_variant = {1: 1, 2: 2, 3: 4, 4: 3, 5: 5}[environment.variant]
        guides.append(_GUIDES[("guide_env", "environment", semantic_variant)])

    if reception.status == "CAUTION" and reception.kind == "device_power":
        guides.append(_GUIDES[("guide_device_power", "device_data", 1)])
    elif reception.status == "CAUTION" and reception.kind == "device_position":
        guides.append(_GUIDES[("guide_device_pos", "device_data", 1)])

    report_statuses = (
        activity.movement.status,
        activity.remote_control.status,
        environment.status,
        reception.status,
        assess_risk_score(metrics.current.risk_score_avg).status,
    )
    if (
        not guides
        and all(status == "GOOD" for status in report_statuses)
        and metrics.current.risk_detected_count == 0
    ):
        guides.append(_GUIDES[("guide_stable", "overall", 1)])

    return guides[:3]


_GUIDES: dict[tuple[GuideType, str, int], GuardianGuide] = {
    ("guide_activity", "movement_count", 1): GuardianGuide(
        guide_type="guide_activity",
        source="movement_count",
        status="RISK",
        variant=1,
        condition_label="움직임 감소",
        title="안부 확인이 필요해요",
        analysis="움직임이 많이 줄었어요.",
    ),
    ("guide_activity", "movement_count", 2): GuardianGuide(
        guide_type="guide_activity",
        source="movement_count",
        status="RISK",
        variant=2,
        condition_label="움직임 증가",
        title="생활 변화를 확인해 주세요",
        analysis="움직임이 평소보다 크게 늘었어요.",
    ),
    ("guide_activity", "remote_control_count", 3): GuardianGuide(
        guide_type="guide_activity",
        source="remote_control_count",
        status="RISK",
        variant=3,
        condition_label="리모컨 감소",
        title="생활 확인이 필요해요",
        analysis="리모컨 사용이 많이 줄었어요.",
    ),
    ("guide_activity", "remote_control_count", 4): GuardianGuide(
        guide_type="guide_activity",
        source="remote_control_count",
        status="RISK",
        variant=4,
        condition_label="리모컨 증가",
        title="안부 전화를 권해요",
        analysis="리모컨 사용이 반복적으로 많았어요.",
    ),
    ("guide_env", "environment", 1): GuardianGuide(
        guide_type="guide_env",
        source="environment",
        status="RISK",
        variant=1,
        condition_label="습도 낮음",
        title="실내가 건조해요",
        analysis="실내가 많이 건조해 가습이나 환기 상태를 확인해 주세요.",
    ),
    ("guide_env", "environment", 2): GuardianGuide(
        guide_type="guide_env",
        source="environment",
        status="RISK",
        variant=2,
        condition_label="습도 높음",
        title="실내가 습해요",
        analysis="실내가 많이 습해 곰팡이나 냄새가 생길 수 있어요.",
    ),
    ("guide_env", "environment", 3): GuardianGuide(
        guide_type="guide_env",
        source="environment",
        status="RISK",
        variant=3,
        condition_label="온도 높음",
        title="실내가 더워요",
        analysis="실내 온도가 높아 냉방이나 환기 상태를 확인해 주세요.",
    ),
    ("guide_env", "environment", 4): GuardianGuide(
        guide_type="guide_env",
        source="environment",
        status="RISK",
        variant=4,
        condition_label="온도 낮음",
        title="실내가 추워요",
        analysis="실내 온도가 낮아 난방 상태를 확인해 주세요.",
    ),
    ("guide_env", "environment", 5): GuardianGuide(
        guide_type="guide_env",
        source="environment",
        status="RISK",
        variant=5,
        condition_label="온도 및 습도 권장 범위 이탈 반복",
        title="생활 환경을 확인해 주세요",
        analysis="실내 온도와 습도가 권장 범위 이탈이 반복되었어요.",
    ),
    ("guide_device_power", "device_data", 1): GuardianGuide(
        guide_type="guide_device_power",
        source="device_data",
        status="CAUTION",
        variant=1,
        condition_label="전원뽑음 주의",
        title="전원 확인이 필요해요",
        analysis="기기 전원이 빠진 이력이 있어요.",
    ),
    ("guide_device_pos", "device_data", 1): GuardianGuide(
        guide_type="guide_device_pos",
        source="device_data",
        status="CAUTION",
        variant=1,
        condition_label="기기위치변경 주의",
        title="기기 위치 확인이 필요해요",
        analysis="움직임·리모컨 사용이 적게 확인됐어요.",
    ),
    ("guide_device_no_data", "device_data", 1): GuardianGuide(
        guide_type="guide_device_no_data",
        source="device_data",
        status="CAUTION",
        variant=1,
        condition_label="센서 자료 부족",
        title="기기 전원이 연결되어 있는지 확인해 주세요",
        analysis="지난 한 주 기기 데이터 수신이 확인되지 않았어요.",
    ),
    ("guide_stable", "overall", 1): GuardianGuide(
        guide_type="guide_stable",
        source="overall",
        status="GOOD",
        variant=1,
        condition_label="상태 양호",
        title="꾸준히 안부를 확인해 주세요",
        analysis="지난 한 주는 큰 이상 없이 안정적인 흐름을 보였어요.",
    ),
}
