"""Grounded Markdown composition; every number comes from Python metrics."""

from __future__ import annotations

from datetime import date, time, timedelta

from ax_contracts import (
    NarrativeGenerationMetadata,
    WardWeeklyMetrics,
    WardWeeklyReport,
    WeeklyNarrative,
)

from .environment_policy import EnvironmentAssessment, assess_environment
from .risk_score_policy import (
    RiskScoreAssessment,
    assess_risk_score,
    risk_score_description,
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
    environment = assess_environment(metrics)
    risk_score = assess_risk_score(current.risk_score_avg)
    report_end = metrics.week_end - timedelta(days=1)
    fallback_note = (
        "\n> 문구 생성이 어려워 검증된 안내 문구로 자동 대체됨\n"
        if generation_mode == "template_fallback"
        else ""
    )
    suggestions = _render_suggestions(narrative)
    summary_suggestion = _summary_suggestion(narrative)
    include_sleep = _has_sleep_data(metrics)
    sleep_section = _render_sleep_section(metrics) if include_sleep else ""
    activity_number = 2 if include_sleep else 1
    environment_number = activity_number + 1
    reception_number = environment_number + 1
    risk_number = reception_number + 1

    markdown = f"""# 주간 생활 리포트

## 기본 정보

- 가입자: {metrics.display_name}
- 주차: {_week_label(metrics.week_start)}
- 기간: {_dated_weekday(metrics.week_start)} ~ {_dated_weekday(report_end)}
- 가입자 상태 점수: {_risk_score(risk_score)}
- 상태 안내: {risk_score_description(risk_score)}

## 한주 총평

{narrative.headline}

{narrative.analysis_text}
{fallback_note}
{summary_suggestion}

---

# 주요 내용

{sleep_section}## {activity_number}. 활동량

- 상태: {_activity_status(metrics)}
- 설명: {_activity_description(metrics)}

### 지표

- 일 평균 움직임
  - 이번 주: {_number(current.movement_count_avg, "회")}
  - 지난주: {_number(previous.movement_count_avg, "회")}

- 일 평균 리모컨 사용
  - 이번 주: {_number(current.remote_control_count_avg, "회")}
  - 지난주: {_number(previous.remote_control_count_avg, "회")}

---

## {environment_number}. 실내 환경

- 상태: {_environment_status(environment)}
- 설명: {_environment_description(environment)}

### 지표

- 최고 / 최저 온도
  - 최고: {_number(current.temperature_max, "℃")}
  - 최저: {_number(current.temperature_min, "℃")}
  - 적정 범위: {_range(environment.temperature_low, environment.temperature_high, "℃")}

- 최고 / 최저 습도
  - 최고: {_number(current.humidity_max, "%")}
  - 최저: {_number(current.humidity_min, "%")}
  - 적정 범위: {_range(environment.humidity_low, environment.humidity_high, "%")}

---

## {reception_number}. 기기 데이터 수신

- 상태: {_reception_status(current.covered_days)}
- 설명: {_reception_description(current.covered_days)}

### 지표

- 자료가 있는 날
  - 이번 주: {current.covered_days}일
  - 지난주: {previous.covered_days}일

- 확인된 기기
  - 이번 주: {current.device_count}대
  - 지난주: {previous.device_count}대

---

## {risk_number}. 위험 관리

- 상태: {_risk_status(current.dispatch_request_count)}
- 설명: {_risk_description(current.dispatch_request_count)}

### 지표

- 위험 감지 / 정상 해제
  - 위험 감지: {current.risk_detected_count}회
  - 정상 해제: {current.risk_resolved_count}회
  - 지난주: {previous.risk_detected_count}회 / {previous.risk_resolved_count}회

- 출동 요청
  - 이번 주: {current.dispatch_request_count}회
  - 지난주: {previous.dispatch_request_count}회

### 위험 관리 기록

- 상세 기록은 현재 주간 리포트 데이터에 포함되지 않아요.

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


def _clock(value: time | None) -> str:
    if value is None:
        return "자료 없음"
    period = "오전" if value.hour < 12 else "오후"
    hour = value.hour % 12 or 12
    return f"{period} {hour:02d}:{value.minute:02d}"


def _has_sleep_data(metrics: WardWeeklyMetrics) -> bool:
    current = metrics.current
    return any(
        value is not None
        for value in (
            current.sleep_time_avg,
            current.wake_up_time_avg,
            current.night_awake_count_avg,
        )
    )


def _render_sleep_section(metrics: WardWeeklyMetrics) -> str:
    current = metrics.current
    previous = metrics.previous
    return f"""## 1. 수면 패턴

- 상태: {_sleep_status(metrics)}
- 설명: {_sleep_description(metrics)}

### 지표

- 평균 취침 시간
  - 이번 주: {_clock(current.sleep_time_avg)}
  - 지난주: {_clock(previous.sleep_time_avg)}

- 평균 기상 시간
  - 이번 주: {_clock(current.wake_up_time_avg)}
  - 지난주: {_clock(previous.wake_up_time_avg)}

- 평균 새벽 각성
  - 이번 주: {_number(current.night_awake_count_avg, "회")}
  - 지난주: {_number(previous.night_awake_count_avg, "회")}

---

"""


def _sleep_status(metrics: WardWeeklyMetrics) -> str:
    current = metrics.current
    if (
        current.sleep_time_avg is None
        and current.wake_up_time_avg is None
        and current.night_awake_count_avg is None
    ):
        return "자료 없음"
    change = metrics.delta.night_awake_count_avg
    if change is None:
        return "주간 비교 어려움"
    if change > 0:
        return "새벽 각성 늘어남"
    if change < 0:
        return "새벽 각성 줄어듦"
    return "수면 흐름 비슷"


def _sleep_description(metrics: WardWeeklyMetrics) -> str:
    status = _sleep_status(metrics)
    descriptions = {
        "자료 없음": "이번 주 수면 자료가 없어요.",
        "주간 비교 어려움": "지난주와 비교할 수 있는 수면 자료가 부족해요.",
        "새벽 각성 늘어남": "평균 새벽 각성이 지난주보다 늘어난 흐름이 보여요.",
        "새벽 각성 줄어듦": "평균 새벽 각성이 지난주보다 줄어든 흐름이 보여요.",
        "수면 흐름 비슷": "평균 새벽 각성이 지난주와 비슷하게 이어졌어요.",
    }
    return descriptions[status]


def _activity_status(metrics: WardWeeklyMetrics) -> str:
    change = metrics.delta.movement_count_avg
    if metrics.current.movement_count_avg is None:
        return "자료 없음"
    if change is None:
        return "주간 비교 어려움"
    if change > 0:
        return "움직임 늘어남"
    if change < 0:
        return "움직임 줄어듦"
    return "움직임 비슷"


def _activity_description(metrics: WardWeeklyMetrics) -> str:
    status = _activity_status(metrics)
    descriptions = {
        "자료 없음": "이번 주 활동 자료가 없어요.",
        "주간 비교 어려움": "지난주와 비교할 수 있는 활동 자료가 부족해요.",
        "움직임 늘어남": "일 평균 움직임이 지난주보다 늘어난 흐름이 보여요.",
        "움직임 줄어듦": "일 평균 움직임이 지난주보다 줄어든 흐름이 보여요.",
        "움직임 비슷": "일 평균 움직임이 지난주와 비슷하게 이어졌어요.",
    }
    return descriptions[status]


def _range(low: float, high: float, suffix: str) -> str:
    return f"{low:g}~{high:g}{suffix}"


def _environment_status(assessment: EnvironmentAssessment) -> str:
    return {
        "unavailable": "자료 없음",
        "good": "양호",
        "caution": "주의",
        "risk": "위험",
    }[assessment.overall_status]


def _environment_description(assessment: EnvironmentAssessment) -> str:
    if assessment.overall_status == "unavailable":
        return "이번 주 최고 온도와 최고 습도 자료가 없어요."
    if assessment.temperature_status == "unavailable":
        return _humidity_description(assessment, disclose_missing=True)
    if assessment.humidity_status == "unavailable":
        return _temperature_description(assessment, disclose_missing=True)
    if assessment.overall_status == "good":
        return "이번 주 최고 온도와 최고 습도는 생활하기 좋은 범위에 있었어요."
    temperature_concern = assessment.temperature_status in {"caution", "risk"}
    humidity_concern = assessment.humidity_status in {"caution", "risk"}
    if temperature_concern and humidity_concern:
        if assessment.overall_status == "caution":
            return "이번 주 최고 온도와 최고 습도가 권장 범위를 벗어나 확인이 필요해요."
        return "이번 주 최고 온도와 최고 습도가 크게 벗어나 냉난방·환기 상태 확인이 필요해요."
    if assessment.temperature_status == assessment.overall_status:
        return _temperature_description(assessment)
    return _humidity_description(assessment)


def _temperature_description(
    assessment: EnvironmentAssessment,
    *,
    disclose_missing: bool = False,
) -> str:
    maximum = assessment.temperature_max
    if maximum is None:
        return "이번 주 최고 온도 자료가 없어요."
    missing = " 최고 습도 자료는 없어요." if disclose_missing else ""
    if assessment.temperature_status == "good":
        return f"이번 주 최고 온도는 해당 월 권장 범위에 있었어요.{missing}"
    direction = "낮아" if maximum < assessment.temperature_low else "높아"
    if assessment.temperature_status == "caution":
        return f"이번 주 최고 온도가 권장 범위보다 {direction} 생활하기 불편할 수 있어요.{missing}"
    return f"이번 주 최고 온도가 권장 범위보다 크게 {direction} 냉난방 상태 확인이 필요해요.{missing}"


def _humidity_description(
    assessment: EnvironmentAssessment,
    *,
    disclose_missing: bool = False,
) -> str:
    maximum = assessment.humidity_max
    if maximum is None:
        return "이번 주 최고 습도 자료가 없어요."
    missing = " 최고 온도 자료는 없어요." if disclose_missing else ""
    if assessment.humidity_status == "good":
        return f"이번 주 최고 습도는 적정 범위에 있었어요.{missing}"
    if assessment.humidity_status == "caution":
        return f"이번 주 최고 습도가 적정 범위를 벗어나 주의가 필요해요.{missing}"
    condition = "건조한" if maximum < assessment.humidity_low else "습한"
    return f"이번 주 최고 습도가 크게 벗어나 {condition} 실내 환경이 확인됐어요. 환기 상태를 살펴봐 주세요.{missing}"


def _reception_status(covered_days: int) -> str:
    if covered_days == 7:
        return "자료 수신 확인"
    if covered_days == 0:
        return "자료 수신 없음"
    return "일부 자료 확인 필요"


def _reception_description(covered_days: int) -> str:
    if covered_days == 7:
        return "이번 주 매일 생활 자료가 확인됐어요."
    if covered_days == 0:
        return "이번 주 확인된 생활 자료가 없어요."
    return "자료가 확인되지 않은 날이 있어 기기 상태를 살펴봐 주세요."


def _risk_status(dispatch_count: int) -> str:
    return "출동 요청 없음" if dispatch_count == 0 else "출동 요청 있음"


def _risk_description(dispatch_count: int) -> str:
    if dispatch_count == 0:
        return "이번 주 출동 요청은 없었어요."
    return "이번 주 출동 요청 기록이 있어 처리 상태를 함께 확인해 주세요."


def _render_suggestions(narrative: WeeklyNarrative) -> str:
    suggestions = narrative.suggestions or [
        "평소 생활 흐름과 함께 가볍게 살펴보셔도 좋아요."
    ]
    sections = []
    for index, suggestion in enumerate(suggestions[:3], start=1):
        observation_index = min(index - 1, len(narrative.observations) - 1)
        evidence = narrative.observations[observation_index]
        sections.append(
            f"## {index}. {suggestion.rstrip('.')}\n\n"
            f"- 근거: {evidence}\n"
            f"- 권장 행동: {suggestion}"
        )
    return "\n\n".join(sections)


def _summary_suggestion(narrative: WeeklyNarrative) -> str:
    suggestion = (
        narrative.suggestions[0]
        if narrative.suggestions
        else "평소 생활 흐름과 함께 가볍게 살펴보셔도 좋아요."
    )
    if suggestion.startswith("이번 주"):
        return suggestion
    return f"이번 주에는 {suggestion}"
