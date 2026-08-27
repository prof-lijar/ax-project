"""Deterministic activity, environment, and device weekly-summary outline."""

from __future__ import annotations

from ax_contracts import WardWeeklyMetrics

from .activity_policy import ActivityMetricAssessment, assess_activity
from .device_reception_policy import assess_device_reception
from .environment_policy import EnvironmentAssessment, assess_environment
from .models import DataQualityCode, SummaryMode, SummaryOutline

_SEVERITY = {"GOOD": 0, "CAUTION": 1, "RISK": 2}


def build_weekly_summary_outline(metrics: WardWeeklyMetrics) -> SummaryOutline:
    """Build the required INTRO/ACTIVITY/ENV/DEVICE/CLOSE summary plan."""

    activity = assess_activity(metrics)
    environment = assess_environment(metrics)
    reception = assess_device_reception(metrics.current)
    activity_status = _worst_available_status(
        activity.movement.status, activity.remote_control.status
    )
    quality_code = _data_quality_code(metrics, reception.kind)
    topic_statuses = {
        "활동": activity_status,
        "환경": environment.status,
        "기기": reception.status,
    }
    good_topics = [
        topic for topic, status in topic_statuses.items() if status == "GOOD"
    ]
    issue_topics = [
        topic
        for topic, status in topic_statuses.items()
        if status in {"CAUTION", "RISK"}
    ]
    mode = _summary_mode(quality_code, topic_statuses)
    life = _life_sentence(
        quality_code,
        activity.movement,
        activity.remote_control,
    )
    environment_text = _environment_sentence(
        environment,
        quality_code,
        connected=life is not None,
    )
    safety = _safety_sentence(
        quality_code,
        reception.kind,
        reception.power_count,
        reception.position_count,
        connected=life is not None or environment_text is not None,
    )
    available_items = _summary_items(life, environment_text, safety)
    all_items = ["움직임", "리모컨", "실내 환경", "기기 데이터 수신"]
    return SummaryOutline(
        mode=mode,
        valid_days=metrics.current.covered_days,
        data_quality_code=quality_code,
        headline=_headline(
            mode,
            quality_code,
            good_topics,
            issue_topics,
            metrics.display_name,
        ),
        life=life,
        environment=environment_text,
        safety=safety,
        close=_close_sentence(mode, quality_code, topic_statuses),
        good_topic_list=good_topics,
        issue_topic_list=issue_topics,
        available_item_list=available_items,
        omitted_item_list=[item for item in all_items if item not in available_items],
    )


def _data_quality_code(
    metrics: WardWeeklyMetrics, reception_kind: str
) -> DataQualityCode:
    if metrics.current.covered_days < 4:
        return "LOW_DATA"
    if reception_kind == "device_power":
        return "PARTIAL_POWER"
    if reception_kind == "device_position":
        return "PARTIAL_POSITION"
    return "VALID"


def _summary_mode(
    quality_code: DataQualityCode,
    topic_statuses: dict[str, str],
) -> SummaryMode:
    if quality_code == "LOW_DATA":
        return "LOW_DATA"
    if quality_code in {"PARTIAL_POWER", "PARTIAL_POSITION"}:
        return "PARTIAL_DEVICE"
    available_statuses = [
        status for status in topic_statuses.values() if status != "UNAVAILABLE"
    ]
    if any(status == "RISK" for status in available_statuses):
        return "RISK"
    if all(status == "GOOD" for status in available_statuses):
        return "ALL_GOOD"
    return "MIXED"


def _life_sentence(
    quality_code: DataQualityCode,
    movement: ActivityMetricAssessment,
    remote: ActivityMetricAssessment,
) -> str | None:
    scope = "확인된 범위에서 " if quality_code != "VALID" else ""
    activity_text = _activity_sentence(movement, remote)
    if activity_text:
        return f"{scope}{activity_text}"
    return "움직임과 리모컨 사용량은 2주 전과 비교할 자료가 부족합니다."


def _activity_sentence(
    movement: ActivityMetricAssessment,
    remote: ActivityMetricAssessment,
) -> str | None:
    activity_parts = [
        (assessment, subject)
        for assessment, subject in (
            (movement, "움직임"),
            (remote, "리모컨 사용"),
        )
        if assessment.status != "UNAVAILABLE"
    ]
    if not activity_parts:
        return None
    activity_parts.sort(key=lambda item: _SEVERITY[item[0].status])
    if len(activity_parts) == 1:
        assessment, subject = activity_parts[0]
        return f"{_activity_phrase(assessment, subject, linked=False)}."
    first, second = activity_parts
    if movement.status == remote.status == "GOOD":
        return "움직임과 리모컨 사용량은 2주 전과 비슷한 수준으로 확인되었습니다."
    return (
        f"{_activity_phrase(first[0], first[1], linked=True)}, "
        f"{_activity_phrase(second[0], second[1], linked=False)}."
    )


def _activity_phrase(
    assessment: ActivityMetricAssessment,
    subject: str,
    *,
    linked: bool,
) -> str:
    ending = {
        ("GOOD", "stable"): (
            "2주 전과 비슷하게 유지되었고",
            "2주 전과 비슷하게 유지되었습니다",
        ),
        ("CAUTION", "decrease"): (
            "2주 전보다 줄어든 흐름을 보였고",
            "2주 전보다 줄어든 흐름을 보였습니다",
        ),
        ("CAUTION", "increase"): (
            "2주 전보다 늘어난 흐름을 보였고",
            "2주 전보다 늘어난 흐름을 보였습니다",
        ),
        ("RISK", "decrease"): (
            "2주 전보다 크게 줄었고",
            "2주 전보다 크게 줄었습니다",
        ),
        ("RISK", "increase"): (
            "2주 전보다 크게 늘었고",
            "2주 전보다 크게 늘었습니다",
        ),
    }[(assessment.status, assessment.trend)][0 if linked else 1]
    return f"{subject}은 {ending}"


def _environment_sentence(
    assessment: EnvironmentAssessment,
    quality_code: DataQualityCode,
    *,
    connected: bool,
) -> str | None:
    connector = "이와 함께 " if connected else ""
    scope = (
        "확인된 범위에서 "
        if quality_code in {"LOW_DATA", "PARTIAL_POWER", "PARTIAL_POSITION"}
        else ""
    )
    if assessment.status == "UNAVAILABLE" or assessment.variant is None:
        return (
            f"{connector}실내 온도와 습도 상태를 판단할 "
            "자료가 부족합니다."
        )
    if assessment.status == "GOOD":
        return f"{connector}{scope}실내 온도와 습도는 대체로 쾌적한 범위에 있었습니다."
    detail = {
        (
            "CAUTION",
            1,
        ): "습도에 주의가 필요한 시간이 있어 환기 상태를 확인할 필요가 있습니다",
        (
            "CAUTION",
            2,
        ): "온도가 불편할 수 있는 구간에 있어 냉난방 상태를 확인할 필요가 있습니다",
        (
            "CAUTION",
            3,
        ): "온도와 습도 변화가 이어져 냉난방과 환기 상태를 확인할 필요가 있습니다",
        ("RISK", 1): "건조한 환경이 반복되어 가습과 환기 상태를 살펴볼 필요가 있습니다",
        ("RISK", 2): "습한 환경이 반복되어 제습과 환기 상태를 살펴볼 필요가 있습니다",
        ("RISK", 3): "추운 구간이 반복되어 난방 상태를 살펴볼 필요가 있습니다",
        ("RISK", 4): "더운 구간이 반복되어 냉방과 환기 상태를 살펴볼 필요가 있습니다",
        (
            "RISK",
            5,
        ): "권장 범위 이탈이 여러 날 이어져 냉난방과 환기 상태를 살펴볼 필요가 있습니다",
    }[(assessment.status, assessment.variant)]
    return f"{connector}{scope}실내 온도와 습도를 함께 살펴본 결과, {detail}."


def _safety_sentence(
    quality_code: DataQualityCode,
    reception_kind: str,
    power_count: int | None,
    position_count: int | None,
    *,
    connected: bool,
) -> str | None:
    connector = "또한 " if connected else ""
    if reception_kind == "device_good":
        scope = "확인된 범위의 " if quality_code == "LOW_DATA" else ""
        device = f"{scope}기기 데이터는 정상적으로 수집되었습니다."
    elif reception_kind == "device_power":
        device = f"기기 전원 분리 패턴이 {power_count or 0}회 확인되어 일부 데이터가 끊겼을 수 있습니다."
    elif reception_kind == "device_position":
        device = f"기기 위치 확인이 필요한 패턴이 {position_count or 0}회 나타나 일부 데이터가 불완전할 수 있습니다."
    else:
        device = (
            "기기 데이터 수신이 확인되지 않아 전원 연결 상태를 "
            "확인할 필요가 있습니다."
        )
    return f"{connector}{device}"


def _worst_available_status(*statuses: str) -> str:
    available = [status for status in statuses if status != "UNAVAILABLE"]
    return max(available, key=_SEVERITY.__getitem__) if available else "UNAVAILABLE"


def _summary_items(
    life: str | None,
    environment: str | None,
    safety: str | None,
) -> list[str]:
    items: list[str] = []
    if life:
        items.extend(("움직임", "리모컨"))
    if environment:
        items.append("실내 환경")
    if safety:
        items.append("기기 데이터 수신")
    return items


def _headline(
    mode: SummaryMode,
    quality_code: DataQualityCode,
    good_topics: list[str],
    issue_topics: list[str],
    display_name: str,
) -> str:
    subscriber = _subscriber_name(display_name)
    if mode == "LOW_DATA":
        return f"지난 한 주 {subscriber}의 생활은 확인된 자료 범위 안에서 세심하게 살펴보았습니다."
    if mode == "PARTIAL_DEVICE":
        cause = "기기 전원" if quality_code == "PARTIAL_POWER" else "기기 위치"
        return f"지난 한 주 {subscriber}의 생활은 {cause} 확인이 필요한 기록을 고려해 정상 수신된 자료를 중심으로 살펴보았습니다."
    good = "·".join(_topic_label(topic) for topic in good_topics)
    issues = "·".join(_topic_label(topic) for topic in issue_topics)
    if mode == "ALL_GOOD":
        return f"지난 한 주 {subscriber}은 대체로 안정적인 생활 흐름을 유지하셨습니다."
    if mode == "RISK":
        return f"지난 한 주 {subscriber}의 {issues}에서 세심한 확인이 필요한 변화가 나타났습니다."
    if good:
        return f"지난 한 주 {subscriber}의 {good}은 안정적이었지만 {issues}에서 확인이 필요한 변화가 함께 나타났습니다."
    return f"지난 한 주 {subscriber}의 {issues}에서 확인이 필요한 변화가 함께 나타났습니다."


def _subscriber_name(display_name: str) -> str:
    name = display_name.strip()
    return name if name.endswith("님") else f"{name}님"


def _topic_label(topic: str) -> str:
    return {
        "환경": "실내 환경",
        "기기": "기기 상태",
    }.get(topic, topic)


def _close_sentence(
    mode: SummaryMode,
    quality_code: DataQualityCode,
    topic_statuses: dict[str, str],
) -> str:
    if mode == "ALL_GOOD":
        return "이번 주에는 평소처럼 안부를 확인하며 현재의 생활 흐름을 유지해 주세요."
    if mode == "LOW_DATA":
        return "이번 주에는 기기 전원 연결 상태를 확인해 주시고, 생활환경을 함께 살펴봐 주세요."
    if mode == "PARTIAL_DEVICE":
        target = "기기 전원 연결" if quality_code == "PARTIAL_POWER" else "기기 위치"
        return f"이번 주에는 안부를 확인하고, {target} 상태도 함께 점검해 주세요."
    if topic_statuses["활동"] == "RISK":
        return "이번 주에는 안부를 확인하고 실제 생활 상태를 함께 살펴봐 주세요."
    if topic_statuses["환경"] in {"CAUTION", "RISK"}:
        return "이번 주에는 안부를 확인하고, 실내 환경도 함께 점검해 주세요."
    if topic_statuses["기기"] in {"CAUTION", "RISK"}:
        return "이번 주에는 안부를 확인하고, 기기 상태도 함께 점검해 주세요."
    return "이번 주에는 안부를 확인하며 주의가 필요한 생활 흐름을 함께 살펴봐 주세요."
