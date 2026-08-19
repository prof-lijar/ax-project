"""Grounded Markdown composition; every number comes from Python metrics."""

from __future__ import annotations

from datetime import time

from ax_contracts import (
    NarrativeGenerationMetadata,
    WardWeeklyMetrics,
    WardWeeklyReport,
    WeeklyNarrative,
)


def render_report(
    metrics: WardWeeklyMetrics,
    narrative: WeeklyNarrative,
    generation_mode: str,
    generation: NarrativeGenerationMetadata,
) -> WardWeeklyReport:
    current = metrics.current
    previous = metrics.previous
    delta = metrics.delta
    suggestions = "\n".join(f"- {item}" for item in narrative.suggestions) or "- 별도 제안이 없습니다."
    observations = "\n".join(f"- {item}" for item in narrative.observations)
    fallback_note = (
        "\n> 문구 생성이 어려워 검증된 안내 문구로 자동 대체됨\n"
        if generation_mode == "template_fallback"
        else ""
    )
    markdown = f"""# {metrics.display_name} 주간 리포트

기간: {metrics.week_start.isoformat()} ~ {metrics.week_end.isoformat()} (종료일 제외)

## {narrative.headline}

{narrative.analysis_text}

## 주요 관찰

{observations}

## 핵심 지표

| 항목 | 이번 주 | 지난주 | 변화 |
| --- | ---: | ---: | ---: |
| 자료가 있는 날 | {current.covered_days}일 | {previous.covered_days}일 | {_signed(delta.covered_days, '일')} |
| 위험 감지일 | {current.danger_days}일 | {previous.danger_days}일 | {_signed(delta.danger_days, '일')} |
| 위험 감지 횟수 | {current.risk_detected_count}회 | {previous.risk_detected_count}회 | {_signed(delta.risk_detected_count, '회')} |
| 출동 요청 | {current.dispatch_request_count}건 | {previous.dispatch_request_count}건 | {_signed(delta.dispatch_request_count, '건')} |
| 미해결 출동 | {current.unresolved_dispatch_count}건 | {previous.unresolved_dispatch_count}건 | {_signed(delta.unresolved_dispatch_count, '건')} |
| 평균 움직임 | {_number(current.movement_count_avg)} | {_number(previous.movement_count_avg)} | {_signed_optional(delta.movement_count_avg)} |
| 평균 리모컨 조작 | {_number(current.remote_control_count_avg)} | {_number(previous.remote_control_count_avg)} | {_signed_optional(delta.remote_control_count_avg)} |
| 평균 불 켜진 시간 | {_number(current.light_on_time_minutes_avg, '분')} | {_number(previous.light_on_time_minutes_avg, '분')} | {_signed_optional(delta.light_on_time_minutes_avg, '분')} |
| 평균 기상 시각 | {_clock(current.wake_up_time_avg)} | {_clock(previous.wake_up_time_avg)} | {_signed_optional(delta.wake_up_time_minutes, '분')} |
| 평균 취침 시각 | {_clock(current.sleep_time_avg)} | {_clock(previous.sleep_time_avg)} | {_signed_optional(delta.sleep_time_minutes, '분')} |

## 실내 환경

| 항목 | 평균 | 최저 | 최고 | 측정 수 |
| --- | ---: | ---: | ---: | ---: |
| 온도 | {_number(current.temperature_avg)} | {_number(current.temperature_min)} | {_number(current.temperature_max)} | {current.temperature_count} |
| 습도 | {_number(current.humidity_avg)} | {_number(current.humidity_min)} | {_number(current.humidity_max)} | {current.humidity_count} |
| 조도 | {_number(current.light_avg)} | {_number(current.light_min)} | {_number(current.light_max)} | {current.light_count} |

## 다음 주 제안

{suggestions}
{fallback_note}"""
    return WardWeeklyReport(
        ward_id=metrics.ward_id,
        display_name=metrics.display_name,
        metrics=metrics,
        narrative=narrative,
        markdown=markdown,
        generation_mode=generation_mode,
        generation=generation,
    )


def _number(value: float | None, suffix: str = "") -> str:
    return "자료 없음" if value is None else f"{value:.1f}{suffix}"


def _clock(value: time | None) -> str:
    return "자료 없음" if value is None else value.strftime("%H:%M")


def _signed(value: int, suffix: str) -> str:
    return f"{value:+d}{suffix}"


def _signed_optional(value: float | None, suffix: str = "") -> str:
    return "비교 불가" if value is None else f"{value:+.1f}{suffix}"
