"""Convert verified metrics into a structured qualitative summary package."""

from ax_contracts import WardWeeklyMetrics

from .activity_policy import activity_description, assess_activity
from .device_reception_policy import (
    assess_device_reception,
    device_reception_description,
)
from .guardian_guidance_policy import build_guardian_guides
from .models import FactPackage, SectionAssessment, SectionStatus
from .summary_policy import build_weekly_summary_outline

_RISK_REPEAT_DAYS = 4
_CAUTION_MIN_DAYS = 2


def build_fact_package(metrics: WardWeeklyMetrics) -> FactPackage:
    """Build the report outline while keeping all arithmetic outside the LLM."""

    current = metrics.current
    coverage = (
        "absent"
        if current.covered_days == 0
        else "complete"
        if current.covered_days == 7
        else "incomplete"
    )
    outline = build_weekly_summary_outline(metrics)
    outline_facts = [
        outline.headline,
        *(
            block
            for block in (outline.life, outline.environment, outline.safety)
            if block
        ),
    ]
    available_items = set(outline.available_item_list)
    allowed_topics = [
        topic
        for topic, included in (
            ("활동", bool({"움직임", "리모컨"} & available_items)),
            ("실내 환경", "실내 환경" in available_items),
            ("기기 데이터 수신", "기기 데이터 수신" in available_items),
        )
        if included
    ]
    issue_topic_names = {
        "활동": "활동",
        "환경": "실내 환경",
        "기기": "기기 데이터 수신",
    }
    required_topics = [
        issue_topic_names[topic]
        for topic in outline.issue_topic_list
        if issue_topic_names[topic] in allowed_topics
    ]
    if outline.data_quality_code != "VALID":
        allowed_topics.insert(0, "자료 상태")
    guides = build_guardian_guides(metrics)
    guide_actions = [guide.title for guide in guides]
    return FactPackage(
        coverage=coverage,
        facts=outline_facts,
        allowed_topics=allowed_topics,
        required_topics=required_topics,
        suggested_actions=list(dict.fromkeys(guide_actions))[:3],
        section_assessments=_section_assessments(metrics),
        guardian_action_candidates=[
            {
                "source": guide.source,
                "status": guide.status,
                "condition": guide.condition_label,
                "title": guide.title,
                "analysis": guide.analysis,
            }
            for guide in guides
        ],
        summary_outline=outline,
    )


def _section_assessments(metrics: WardWeeklyMetrics) -> list[SectionAssessment]:
    activity = assess_activity(metrics)
    assessments: list[SectionAssessment] = []
    if activity.movement.status != "UNAVAILABLE":
        assessments.append(
            SectionAssessment(
                source="movement_count",
                status=activity.movement.status,
                finding=activity_description("movement", activity.movement),
            )
        )
    if activity.remote_control.status != "UNAVAILABLE":
        assessments.append(
            SectionAssessment(
                source="remote_control_count",
                status=activity.remote_control.status,
                finding=activity_description("remote_control", activity.remote_control),
            )
        )

    current = metrics.current
    for source, departures, low_days, high_days in (
        (
            "temperature",
            current.temperature_out_of_range_days,
            current.low_temperature_days,
            current.high_temperature_days,
        ),
        (
            "humidity",
            current.humidity_out_of_range_days,
            current.low_humidity_days,
            current.high_humidity_days,
        ),
    ):
        status = _dimension_status(departures, low_days, high_days)
        if status is not None:
            assessments.append(
                SectionAssessment(
                    source=source,
                    status=status,
                    finding=_dimension_finding(source, status, low_days, high_days),
                )
            )

    reception = assess_device_reception(current)
    if reception.status != "UNAVAILABLE":
        assessments.append(
            SectionAssessment(
                source="device_data",
                status=reception.status,
                finding=device_reception_description(reception),
            )
        )
    return assessments


def _dimension_status(
    departures: int | None,
    low_days: int | None,
    high_days: int | None,
) -> SectionStatus | None:
    if departures is None or low_days is None or high_days is None:
        return None
    if low_days >= _RISK_REPEAT_DAYS or high_days >= _RISK_REPEAT_DAYS:
        return "RISK"
    if departures >= _CAUTION_MIN_DAYS:
        return "CAUTION"
    return "GOOD"


def _dimension_finding(
    source: str,
    status: SectionStatus,
    low_days: int | None,
    high_days: int | None,
) -> str:
    label = "온도" if source == "temperature" else "습도"
    if status == "GOOD":
        return f"실내 {label}가 대체로 권장 범위에 있었어요."
    if status == "CAUTION":
        return f"실내 {label}의 권장 범위 이탈이 반복됐어요."
    if (low_days or 0) >= _RISK_REPEAT_DAYS:
        direction = "낮은"
    elif (high_days or 0) >= _RISK_REPEAT_DAYS:
        direction = "높은"
    else:
        direction = "권장 범위를 벗어난"
    return f"{direction} 실내 {label}가 반복됐어요."
