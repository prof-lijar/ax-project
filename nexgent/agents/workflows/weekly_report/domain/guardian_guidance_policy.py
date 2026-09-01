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
    description: str
    tag: str
    template_id: str | None


def build_guardian_guides(metrics: WardWeeklyMetrics) -> list[GuardianGuide]:
    """Return at most three approved guides in product-priority order."""

    guides: list[GuardianGuide] = []
    reception = assess_device_reception(metrics.current)
    if reception.kind == "device_no_data":
        guides.append(_GUIDES[("guide_device_no_data", "device_data", 1)])
    elif reception.status == "CAUTION" and reception.kind == "device_power":
        guides.append(_GUIDES[("guide_device_power", "device_data", 1)])
    elif reception.status == "CAUTION" and reception.kind == "device_position":
        guides.append(_GUIDES[("guide_device_pos", "device_data", 1)])

    activity = assess_activity(metrics)
    if activity.movement.status == "RISK" and activity.movement.trend == "decrease":
        variant = 1
        guides.append(_GUIDES[("guide_activity", "movement_count", variant)])
    elif (
        activity.movement.status == "CAUTION" and activity.movement.trend == "increase"
    ):
        guides.append(_GUIDES[("guide_activity", "movement_count", 2)])
    if (
        activity.remote_control.status == "RISK"
        and activity.remote_control.trend == "decrease"
    ):
        guides.append(_GUIDES[("guide_activity", "remote_control_count", 4)])
    elif (
        activity.remote_control.status == "CAUTION"
        and activity.remote_control.trend == "increase"
    ):
        guides.append(_GUIDES[("guide_activity", "remote_control_count", 5)])

    environment = assess_environment(metrics)
    if environment.variant is not None and (
        environment.status == "CAUTION"
        and environment.variant in {1, 2, 3, 4}
        or environment.status == "RISK"
        and environment.variant in {5, 6, 7, 8}
    ):
        guides.append(_GUIDES[("guide_env", "environment", environment.variant)])

    report_area_statuses = (
        activity.movement.status,
        activity.remote_control.status,
        environment.status,
        reception.status,
    )
    risk_score_status = assess_risk_score(metrics.current.risk_score_avg).status
    if (
        not guides
        and risk_score_status == "GOOD"
        and not any(status in {"CAUTION", "RISK"} for status in report_area_statuses)
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
        condition_label="활동 감소",
        title="안부를 한 번 확인해 주세요",
        description="활동이 많이 줄어든 모습이에요.",
        tag="안부 전화하기",
        template_id="ACT_RISK_01",
    ),
    ("guide_activity", "movement_count", 2): GuardianGuide(
        guide_type="guide_activity",
        source="movement_count",
        status="CAUTION",
        variant=2,
        condition_label="활동 증가",
        title="생활에 달라진 점이 있는지 살펴봐 주세요",
        description="활동이 평소보다 많이 늘어난 모습이에요.",
        tag="생활 확인하기",
        template_id="ACT_RISK_02",
    ),
    ("guide_activity", "remote_control_count", 4): GuardianGuide(
        guide_type="guide_activity",
        source="remote_control_count",
        status="RISK",
        variant=4,
        condition_label="생활 패턴 감소",
        title="안부를 한 번 확인해 주세요",
        description="TV 이용 등 일상적인 생활 패턴이 많이 줄었어요.",
        tag="안부 전화하기",
        template_id="ACT_RISK_03",
    ),
    ("guide_activity", "remote_control_count", 5): GuardianGuide(
        guide_type="guide_activity",
        source="remote_control_count",
        status="CAUTION",
        variant=5,
        condition_label="생활 패턴 증가",
        title="최근 생활에 달라진 점이 있는지 살펴봐 주세요",
        description="TV 이용 등 일상적인 생활 패턴이 많이 늘었어요.",
        tag="생활 확인하기",
        template_id="ACT_RISK_04",
    ),
    ("guide_env", "environment", 1): GuardianGuide(
        guide_type="guide_env",
        source="environment",
        status="CAUTION",
        variant=1,
        condition_label="더운 환경",
        title="냉방이나 환기 상태를 확인해 주세요",
        description="집 안이 조금 더운 날이 있었어요.",
        tag="환경 확인하기",
        template_id="ENV_CAUTION_01",
    ),
    ("guide_env", "environment", 2): GuardianGuide(
        guide_type="guide_env",
        source="environment",
        status="CAUTION",
        variant=2,
        condition_label="추운 환경",
        title="난방 상태를 확인해 주세요",
        description="집 안이 조금 추운 날이 있었어요.",
        tag="환경 확인하기",
        template_id="ENV_CAUTION_02",
    ),
    ("guide_env", "environment", 3): GuardianGuide(
        guide_type="guide_env",
        source="environment",
        status="CAUTION",
        variant=3,
        condition_label="습한 환경",
        title="제습이나 환기가 필요한지 살펴봐 주세요",
        description="집 안이 습한 날이 있었어요.",
        tag="환경 확인하기",
        template_id="ENV_CAUTION_03",
    ),
    ("guide_env", "environment", 4): GuardianGuide(
        guide_type="guide_env",
        source="environment",
        status="CAUTION",
        variant=4,
        condition_label="건조한 환경",
        title="실내가 너무 건조하지 않은지 살펴봐 주세요",
        description="집 안이 건조한 날이 있었어요.",
        tag="환경 확인하기",
        template_id="ENV_CAUTION_04",
    ),
    ("guide_env", "environment", 5): GuardianGuide(
        guide_type="guide_env",
        source="environment",
        status="RISK",
        variant=5,
        condition_label="덥고 습한 환경",
        title="냉방과 환기 상태를 함께 확인해 주세요",
        description="덥고 습한 날이 여러 번 이어졌어요.",
        tag="환경 확인하기",
        template_id="ENV_RISK_05",
    ),
    ("guide_env", "environment", 6): GuardianGuide(
        guide_type="guide_env",
        source="environment",
        status="RISK",
        variant=6,
        condition_label="덥고 건조한 환경",
        title="냉방 상태와 실내 습도를 함께 확인해 주세요",
        description="덥고 건조한 날이 여러 번 이어졌어요.",
        tag="환경 확인하기",
        template_id="ENV_RISK_06",
    ),
    ("guide_env", "environment", 7): GuardianGuide(
        guide_type="guide_env",
        source="environment",
        status="RISK",
        variant=7,
        condition_label="춥고 습한 환경",
        title="난방과 환기 상태를 함께 확인해 주세요",
        description="춥고 습한 날이 여러 번 이어졌어요.",
        tag="환경 확인하기",
        template_id="ENV_RISK_07",
    ),
    ("guide_env", "environment", 8): GuardianGuide(
        guide_type="guide_env",
        source="environment",
        status="RISK",
        variant=8,
        condition_label="춥고 건조한 환경",
        title="난방 상태와 실내 습도를 함께 확인해 주세요",
        description="춥고 건조한 날이 여러 번 이어졌어요.",
        tag="환경 확인하기",
        template_id="ENV_RISK_08",
    ),
    ("guide_device_power", "device_data", 1): GuardianGuide(
        guide_type="guide_device_power",
        source="device_data",
        status="CAUTION",
        variant=1,
        condition_label="전원 확인",
        title="기기 전원이 잘 연결되어 있는지 확인해 주세요",
        description="생활 정보가 들어오지 않은 날이 있었어요.",
        tag="기기 확인하기",
        template_id="DEV_POWER_01",
    ),
    ("guide_device_pos", "device_data", 1): GuardianGuide(
        guide_type="guide_device_pos",
        source="device_data",
        status="CAUTION",
        variant=1,
        condition_label="위치 확인",
        title="기기가 제자리에 있는지 확인해 주세요",
        description="생활 정보가 평소보다 적게 들어온 날이 있었어요.",
        tag="기기 확인하기",
        template_id="DEV_POS_01",
    ),
    ("guide_device_no_data", "device_data", 1): GuardianGuide(
        guide_type="guide_device_no_data",
        source="device_data",
        status="CAUTION",
        variant=1,
        condition_label="센서 자료 부족",
        title="기기 전원이 연결되어 있는지 확인해 주세요",
        description="지난 한 주 기기 데이터 수신이 확인되지 않았어요.",
        tag="기기 확인하기",
        template_id=None,
    ),
    ("guide_stable", "overall", 1): GuardianGuide(
        guide_type="guide_stable",
        source="overall",
        status="GOOD",
        variant=1,
        condition_label="상태 양호",
        title="평소처럼 안부를 확인해 주세요",
        description="평소와 비슷한 생활 흐름이 이어지고 있어요.",
        tag="안부 전화하기",
        template_id=None,
    ),
}
