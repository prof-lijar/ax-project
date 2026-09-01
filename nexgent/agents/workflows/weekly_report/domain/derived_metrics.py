"""Convert verified metrics into a structured qualitative summary package."""

from ax_contracts import WardWeeklyMetrics

from .activity_policy import (
    activity_description,
    activity_status_label,
    activity_summary,
    assess_activity,
)
from .device_reception_policy import (
    assess_device_reception,
    device_reception_description,
    device_reception_status_label,
    device_reception_summary,
)
from .environment_policy import (
    assess_environment,
    environment_description,
    environment_status_label,
    environment_summary,
)
from .guardian_guidance_policy import build_guardian_guides
from .models import (
    FactPackage,
    SectionAssessment,
    SectionStatus,
    WeeklySummaryData,
    WeeklySummarySection,
)
from .risk_score_policy import (
    assess_risk_score,
    risk_score_description,
    risk_score_status_label,
)

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
    guides = build_guardian_guides(metrics)
    guide_actions = [guide.title for guide in guides]
    weekly_data = _weekly_summary_data(metrics, guide_actions)
    activity = assess_activity(metrics)
    environment = assess_environment(metrics)
    reception = assess_device_reception(metrics.current)
    allowed_topics = ["활동", "실내 환경", "기기 상태", "위험 감지"]
    if coverage != "complete" or reception.status == "UNAVAILABLE":
        allowed_topics.insert(0, "자료 상태")
    required_topics = []
    if any(
        item.status in {"CAUTION", "RISK"}
        for item in (activity.movement, activity.remote_control)
    ):
        required_topics.append("활동")
    if environment.status in {"CAUTION", "RISK"}:
        required_topics.append("실내 환경")
    if reception.status == "CAUTION":
        required_topics.append("기기 상태")
    return FactPackage(
        coverage=coverage,
        facts=[
            weekly_data.overall.description,
            weekly_data.living_activity.description,
            weekly_data.living_pattern.description,
            weekly_data.indoor_environment.description,
            weekly_data.device_status.description,
            weekly_data.risk_management.description,
        ],
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
                "description": guide.description,
                "tag": guide.tag,
                "template_id": guide.template_id,
            }
            for guide in guides
        ],
        weekly_report_data=weekly_data,
    )


def _weekly_summary_data(
    metrics: WardWeeklyMetrics,
    guide_actions: list[str],
) -> WeeklySummaryData:
    """Build report-facing data without prescribing the summary's sentences."""

    activity = assess_activity(metrics)
    environment = assess_environment(metrics)
    reception = assess_device_reception(metrics.current)
    score = assess_risk_score(metrics.current.risk_score_avg)
    risk_detected = metrics.current.risk_detected_count
    return WeeklySummaryData(
        subscriber=metrics.display_name,
        overall=WeeklySummarySection(
            status=risk_score_status_label(score),
            description=risk_score_description(score),
        ),
        living_activity=WeeklySummarySection(
            status=activity_status_label(activity.movement),
            description=activity_description("movement", activity.movement),
            summary=activity_summary("movement", activity.movement),
        ),
        living_pattern=WeeklySummarySection(
            status=activity_status_label(activity.remote_control),
            description=activity_description("remote_control", activity.remote_control),
            summary=activity_summary("remote_control", activity.remote_control),
        ),
        indoor_environment=WeeklySummarySection(
            status=environment_status_label(environment),
            description=environment_description(environment),
            summary=environment_summary(environment),
        ),
        device_status=WeeklySummarySection(
            status=device_reception_status_label(reception),
            description=device_reception_description(reception),
            summary=device_reception_summary(reception),
        ),
        risk_management=WeeklySummarySection(
            status=("위험 감지 없음" if risk_detected == 0 else "위험 감지 기록 있음"),
            description=(
                "지난 한 주 위험 감지 기록은 없었어요."
                if risk_detected == 0
                else "지난 한 주 위험 감지 기록이 있어 생활 흐름을 함께 확인해 주세요."
            ),
        ),
        guardian_actions=list(dict.fromkeys(guide_actions))[:3],
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
