"""Grounded Markdown composition; every number comes from Python metrics."""

from __future__ import annotations

from datetime import date, timedelta

from ax_contracts import (
    NarrativeGenerationMetadata,
    WardWeeklyMetrics,
    WardWeeklyReport,
    WeeklyNarrative,
)

from .activity_policy import (
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

- 상태: {activity_status_label(activity.movement)}
- 설명: {activity_description("movement", activity.movement)}
- 요약: {activity_summary("movement", activity.movement)}

### 지표

- 지난 한 주: {_number(current.movement_count_total, "회")}
- 2주 전: {_number(previous.movement_count_total, "회")}
- 2주 전과 비교: {_percentage(activity.movement)}

---

## 생활 패턴

- 상태: {activity_status_label(activity.remote_control)}
- 설명: {activity_description("remote_control", activity.remote_control)}
- 요약: {activity_summary("remote_control", activity.remote_control)}

### 지표

- 지난 한 주: {_number(current.remote_control_count_total, "회")}
- 2주 전: {_number(previous.remote_control_count_total, "회")}
- 2주 전과 비교: {_percentage(activity.remote_control)}

---

## 실내 환경

- 상태: {environment_status_label(environment)}
- 설명: {environment_description(environment)}
- 요약: {environment_summary(environment)}

### 지표

- 온습도 관측일: {_days(environment.observed_days)}
- 온도 권장범위 이탈: {_days(environment.temperature_out_of_range_days)}
- 습도 권장범위 이탈: {_days(environment.humidity_out_of_range_days)}
- 온도 또는 습도 권장범위 이탈: {_days(environment.environment_out_of_range_days)}

- 최고 / 최저 온도
  - 최고: {_number(current.temperature_max, "℃")}
  - 최저: {_number(current.temperature_min, "℃")}

- 최고 / 최저 습도
  - 최고: {_number(current.humidity_max, "%")}
  - 최저: {_number(current.humidity_min, "%")}

---

## 기기 상태

- 상태: {device_reception_status_label(reception)}
- 설명: {device_reception_description(reception)}
- 요약: {device_reception_summary(reception)}

### 지표

- 정상 수신: {_count(reception.good_count)}
- 기타 수신 패턴: {_count(reception.other_count)}
- 전원 확인 패턴: {_count(reception.power_count)}
- 기기 위치 확인 패턴: {_count(reception.position_count)}

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
        markdown=markdown,
        generation_mode=generation_mode,
        generation=generation,
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


def _days(value: int | None) -> str:
    return "자료 없음" if value is None else f"{value}일"


def _count(value: int | None) -> str:
    return "자료 없음" if value is None else f"{value}회"


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
        else "- 확인된 자료를 바탕으로 한 별도 행동 제안은 없어요."
    )


def _render_guardian_guide(index: int, guide: GuardianGuide) -> str:
    metadata = [
        f"- 설명: {guide.description}",
        f"- 태그: {guide.tag}",
    ]
    if guide.template_id is not None:
        metadata.append(f"- template_id: {guide.template_id}")
    return f"## {index}. {guide.title}\n\n" + "\n".join(metadata)
