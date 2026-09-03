"""Grounded Markdown composition; every number comes from Python metrics."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from ax_contracts import (
    NarrativeGenerationMetadata,
    WardWeeklyMetrics,
    WardWeeklyMetricSnapshot,
    WardWeeklyReport,
    WeeklyNarrative,
    WeeklyReportActivitySection,
    WeeklyReportBasicInfo,
    WeeklyReportComparisonMetrics,
    WeeklyReportComparisonSection,
    WeeklyReportDeviceMetrics,
    WeeklyReportDeviceSection,
    WeeklyReportEnvironmentMetrics,
    WeeklyReportEnvironmentSection,
    WeeklyReportGuardianAction,
    WeeklyReportGuardianActions,
    WeeklyReportPeriod,
    WeeklyReportRiskMetrics,
    WeeklyReportRiskSection,
    WeeklyReportTemplateData,
)

from .activity_policy import (
    ActivityAssessment,
    ActivityMetric,
    ActivityMetricAssessment,
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
    EnvironmentAssessment,
    assess_environment,
    environment_description,
    environment_status_label,
    environment_summary,
)
from .guardian_guidance_policy import GuardianGuide, build_guardian_guides
from .risk_score_policy import (
    RiskScoreAssessment,
    assess_risk_score,
    risk_score_description,
    risk_score_status_label,
)

_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


def render_report(
    metrics: WardWeeklyMetrics,
    narrative: WeeklyNarrative,
    generation_mode: str,
    generation: NarrativeGenerationMetadata,
) -> WardWeeklyReport:
    """Render the guardian-facing section template from validated values."""

    current = metrics.current
    previous = metrics.previous
    activity = assess_activity(metrics)
    environment = assess_environment(metrics)
    reception = assess_device_reception(current)
    guardian_guides = build_guardian_guides(metrics)
    risk_score = assess_risk_score(current.risk_score_avg)
    selected_period_days = (metrics.week_end - metrics.week_start).days
    normal_reception_days = current.covered_days
    power_check_days = selected_period_days - normal_reception_days
    indoor_environment_description = _environment_description(current, environment)
    report_end = metrics.week_end - timedelta(days=1)
    fallback_note = (
        "\n> 문구 생성이 어려워 검증된 안내 문구로 자동 대체됨\n"
        if generation_mode == "template_fallback"
        else ""
    )
    suggestions = _render_suggestions(narrative, guardian_guides)
    summary_text = " ".join(
        value for value in (narrative.headline, narrative.analysis_text) if value
    )
    template_data = WeeklyReportTemplateData(
        basic_info=WeeklyReportBasicInfo(
            subscriber_name=metrics.display_name,
            week_label=_week_label(metrics.week_start),
            period=WeeklyReportPeriod(
                start_date=metrics.week_start,
                end_date=report_end,
                display_value=(
                    f"{_dated_weekday(metrics.week_start)} ~ "
                    f"{_dated_weekday(report_end)}"
                ),
            ),
            risk_score=risk_score.score,
            risk_score_display=_risk_score(risk_score),
            status=risk_score_status_label(risk_score),
            status_description=risk_score_description(risk_score),
        ),
        weekly_summary=summary_text,
        generation_notice=(
            "문구 생성이 어려워 검증된 안내 문구로 자동 대체됨"
            if generation_mode == "template_fallback"
            else None
        ),
        living_activity=WeeklyReportActivitySection(
            descriptions=_activity_descriptions(activity),
            tag=_activity_tag(activity),
            activity_detection=_comparison_section(
                "활동감지", activity.movement
            ),
            remote_control_usage=_comparison_section(
                "리모컨 이용", activity.remote_control
            ),
        ),
        indoor_environment=WeeklyReportEnvironmentSection(
            status=environment_status_label(environment),
            description=indoor_environment_description,
            tag=environment_summary(environment),
            metrics=WeeklyReportEnvironmentMetrics(
                observed_days=environment.observed_days,
                temperature_out_of_range_days=(
                    environment.temperature_out_of_range_days
                ),
                humidity_out_of_range_days=environment.humidity_out_of_range_days,
                environment_out_of_range_days=(
                    environment.environment_out_of_range_days
                ),
                temperature_max=current.temperature_max,
                temperature_min=current.temperature_min,
                humidity_max=current.humidity_max,
                humidity_min=current.humidity_min,
                observed_days_display=_environment_days(environment.observed_days),
                temperature_out_of_range_days_display=_environment_days(
                    environment.temperature_out_of_range_days
                ),
                humidity_out_of_range_days_display=_environment_days(
                    environment.humidity_out_of_range_days
                ),
                environment_out_of_range_days_display=_environment_days(
                    environment.environment_out_of_range_days
                ),
                temperature_max_display=_environment_number(
                    current.temperature_max, "℃"
                ),
                temperature_min_display=_environment_number(
                    current.temperature_min, "℃"
                ),
                humidity_max_display=_environment_number(current.humidity_max, "%"),
                humidity_min_display=_environment_number(current.humidity_min, "%"),
            ),
        ),
        device_status=WeeklyReportDeviceSection(
            status=device_reception_status_label(reception),
            description=device_reception_description(reception),
            tag=device_reception_summary(reception),
            metrics=WeeklyReportDeviceMetrics(
                normal_reception_days=normal_reception_days,
                other_count=reception.other_count,
                power_check_days=power_check_days,
                position_count=reception.position_count,
                current_covered_days=current.covered_days,
                previous_covered_days=previous.covered_days,
                current_device_count=current.device_count,
                previous_device_count=previous.device_count,
                normal_reception_days_display=f"{normal_reception_days}일",
                other_count_display=_device_count(reception.other_count),
                power_check_days_display=f"{power_check_days}일",
                position_count_display=_device_count(reception.position_count),
                current_covered_days_display=f"{current.covered_days}일",
                previous_covered_days_display=f"{previous.covered_days}일",
                current_device_count_display=f"{current.device_count}대",
                previous_device_count_display=f"{previous.device_count}대",
            ),
        ),
        risk_management=WeeklyReportRiskSection(
            status=_risk_status(current.risk_detected_count),
            description=_risk_description(current.risk_detected_count),
            metrics=WeeklyReportRiskMetrics(
                detected_count=current.risk_detected_count,
                resolved_count=current.risk_resolved_count,
                previous_detected_count=previous.risk_detected_count,
                previous_resolved_count=previous.risk_resolved_count,
                detected_count_display=f"{current.risk_detected_count}회",
                resolved_count_display=f"{current.risk_resolved_count}회",
                previous_counts_display=(
                    f"{previous.risk_detected_count}회 / "
                    f"{previous.risk_resolved_count}회"
                ),
            ),
        ),
        guardian_actions=_guardian_actions(guardian_guides),
    )
    markdown = f"""# 주간 생활 리포트

## 기본 정보

- 가입자: {metrics.display_name}
- 주차: {_week_label(metrics.week_start)}
- 기간: {_dated_weekday(metrics.week_start)} ~ {_dated_weekday(report_end)}
- 가입자 상태 점수: {_risk_score(risk_score)}
- 상태: {risk_score_status_label(risk_score)}
- 상태 안내: {risk_score_description(risk_score)}

## 한주 총평

{summary_text}
{fallback_note}
---

# 주요 내용

## 생활 활동

설명:
{_activity_description_markdown(activity)}
- 태그: {_activity_tag(activity)}

### 활동감지

- 상태: {activity_status_label(activity.movement)}
- 지난 한 주: {_number(current.movement_count_total, "회")}
- 2주 전: {_number(previous.movement_count_total, "회")}
- 2주 전과 비교: {_percentage(activity.movement)}

---

### 리모컨 이용

- 상태: {activity_status_label(activity.remote_control)}
- 지난 한 주: {_number(current.remote_control_count_total, "회")}
- 2주 전: {_number(previous.remote_control_count_total, "회")}
- 2주 전과 비교: {_percentage(activity.remote_control)}

---

## 실내 환경

- 상태: {environment_status_label(environment)}
- 설명: {indoor_environment_description}
- 태그: {environment_summary(environment)}

### 지표

- 온습도 관측일: {_environment_days(environment.observed_days)}
- 온도 권장범위 이탈: {_environment_days(environment.temperature_out_of_range_days)}
- 습도 권장범위 이탈: {_environment_days(environment.humidity_out_of_range_days)}
- 온도 또는 습도 권장범위 이탈: {_environment_days(environment.environment_out_of_range_days)}

- 최고 / 최저 온도
  - 최고: {_environment_number(current.temperature_max, "℃")}
  - 최저: {_environment_number(current.temperature_min, "℃")}

- 최고 / 최저 습도
  - 최고: {_environment_number(current.humidity_max, "%")}
  - 최저: {_environment_number(current.humidity_min, "%")}

---

## 기기 상태

- 상태: {device_reception_status_label(reception)}
- 설명: {device_reception_description(reception)}
- 태그: {device_reception_summary(reception)}

### 지표

- 정보 수신: {normal_reception_days}일
- 기타 수신 패턴: {_device_count(reception.other_count)}
- 전원 확인: {power_check_days}일
- 기기 위치 확인 패턴: {_device_count(reception.position_count)}

- 자료가 있는 날
  - 지난 한 주: {current.covered_days}일
  - 2주 전: {previous.covered_days}일

- 확인된 기기
  - 지난 한 주: {current.device_count}대
  - 2주 전: {previous.device_count}대

---

## 위험 관리

- 상태: {_risk_status(current.risk_detected_count)}
- 설명: {_risk_description(current.risk_detected_count)}

### 지표

- 위험 감지 / 정상 해제
  - 위험 감지: {current.risk_detected_count}회
  - 정상 해제: {current.risk_resolved_count}회
  - 2주 전: {previous.risk_detected_count}회 / {previous.risk_resolved_count}회

---

# 보호자 행동 제안

{suggestions}"""
    return WardWeeklyReport(
        ward_id=metrics.ward_id,
        display_name=metrics.display_name,
        metrics=metrics,
        narrative=narrative,
        template_data=template_data,
        markdown=markdown,
        generation_mode=generation_mode,
        generation=generation,
    )


def _comparison_section(
    title: Literal["활동감지", "리모컨 이용"],
    assessment: ActivityMetricAssessment,
) -> WeeklyReportComparisonSection:
    return WeeklyReportComparisonSection(
        title=title,
        status=activity_status_label(assessment),
        metrics=WeeklyReportComparisonMetrics(
            current_week=assessment.current_total,
            current_week_display=_number(assessment.current_total, "회"),
            previous_week=assessment.previous_total,
            previous_week_display=_number(assessment.previous_total, "회"),
            comparison_percent=assessment.ratio_percent,
            comparison_display=_percentage(assessment),
        ),
    )


def _activity_descriptions(assessment: ActivityAssessment) -> list[str]:
    movement_missing = assessment.movement.status == "UNAVAILABLE"
    remote_missing = assessment.remote_control.status == "UNAVAILABLE"
    if movement_missing and remote_missing:
        return ["지난 주는 생활 활동을 살펴볼 정보가 부족했어요."]
    descriptions = [
        "지난 주는 활동 감지를 살펴볼 정보가 부족했어요."
        if movement_missing
        else activity_description("movement", assessment.movement),
        "지난 주는 리모컨 이용을 살펴볼 정보가 부족했어요."
        if remote_missing
        else activity_description("remote_control", assessment.remote_control),
    ]
    return descriptions


def _activity_description_markdown(assessment: ActivityAssessment) -> str:
    return "\n".join(
        f"- {description}" for description in _activity_descriptions(assessment)
    )


def _activity_tag(assessment: ActivityAssessment) -> str:
    priority = {"GOOD": 0, "UNAVAILABLE": 1, "CAUTION": 2, "RISK": 3}
    candidates: tuple[
        tuple[ActivityMetric, ActivityMetricAssessment],
        tuple[ActivityMetric, ActivityMetricAssessment],
    ] = (
        ("movement", assessment.movement),
        ("remote_control", assessment.remote_control),
    )
    metric, selected = max(candidates, key=lambda item: priority[item[1].status])
    return activity_summary(metric, selected)


def _environment_description(
    snapshot: WardWeeklyMetricSnapshot,
    assessment: EnvironmentAssessment,
) -> str:
    temperature_missing = not _has_temperature_data(snapshot)
    humidity_missing = not _has_humidity_data(snapshot)
    if temperature_missing and humidity_missing:
        return "지난 주는 실내 환경을 살펴볼 정보가 부족했어요."
    if temperature_missing:
        return "지난 주는 온도를 살펴볼 정보가 부족했어요."
    if humidity_missing:
        return "지난 주는 습도를 살펴볼 정보가 부족했어요."
    return environment_description(assessment)


def _has_temperature_data(snapshot: WardWeeklyMetricSnapshot) -> bool:
    return (
        snapshot.temperature_count > 0
        and snapshot.temperature_max is not None
        and snapshot.temperature_min is not None
    )


def _has_humidity_data(snapshot: WardWeeklyMetricSnapshot) -> bool:
    return (
        snapshot.humidity_count > 0
        and snapshot.humidity_max is not None
        and snapshot.humidity_min is not None
    )


def _guardian_actions(guides: list[GuardianGuide]) -> WeeklyReportGuardianActions:
    if not guides:
        return WeeklyReportGuardianActions(
            empty_message="확인된 자료를 바탕으로 한 별도 행동 제안은 없어요.",
            template_id="GUI_GOOD_01",
        )
    return WeeklyReportGuardianActions(
        items=[
            WeeklyReportGuardianAction(
                title=guide.title,
                description=guide.description,
                tag=guide.tag,
                template_id=guide.template_id,
            )
            for guide in guides
        ]
    )


def _week_label(value: date) -> str:
    week = ((value.day - 1) // 7) + 1
    return f"{value.month}월 {week}주차"


def _dated_weekday(value: date) -> str:
    return f"{value.isoformat()}({_WEEKDAYS[value.weekday()]})"


def _number(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "자료 없음"
    rendered = str(int(value)) if value.is_integer() else f"{value:.1f}"
    return f"{rendered}{suffix}"


def _risk_score(assessment: RiskScoreAssessment) -> str:
    if assessment.score is None:
        return "자료 없음"
    return f"{assessment.score}점"


def _percentage(assessment: ActivityMetricAssessment) -> str:
    if assessment.ratio_percent is None:
        return "비교 불가"
    value = assessment.ratio_percent
    rendered = str(int(value)) if value.is_integer() else f"{value:.1f}"
    return f"{rendered}%"


def _environment_number(value: float | None, suffix: str) -> str:
    return "-" if value is None else _number(value, suffix)


def _environment_days(value: int | None) -> str:
    return "-" if value is None else f"{value}일"


def _device_count(value: int | None) -> str:
    return "0" if value is None else f"{value}회"


def _risk_status(risk_detected_count: int) -> str:
    return "위험 감지 없음" if risk_detected_count == 0 else "위험 감지 기록 있음"


def _risk_description(risk_detected_count: int) -> str:
    if risk_detected_count == 0:
        return "지난 한 주 위험 감지 기록은 없었어요."
    return "지난 한 주 위험 감지 기록이 있어 생활 흐름을 함께 확인해 주세요."


def _render_suggestions(
    narrative: WeeklyNarrative,
    guardian_guides: list[GuardianGuide],
) -> str:
    del narrative
    sections = [
        _render_guardian_guide(index, guide)
        for index, guide in enumerate(guardian_guides, start=1)
    ]
    return (
        "\n\n".join(sections)
        if sections
        else (
            "- 확인된 자료를 바탕으로 한 별도 행동 제안은 없어요.\n"
            "- template_id: GUI_GOOD_01"
        )
    )


def _render_guardian_guide(index: int, guide: GuardianGuide) -> str:
    metadata = [
        f"- 설명: {guide.description}",
        f"- 태그: {guide.tag}",
    ]
    if guide.template_id is not None:
        metadata.append(f"- template_id: {guide.template_id}")
    return f"## {index}. {guide.title}\n\n" + "\n".join(metadata)
