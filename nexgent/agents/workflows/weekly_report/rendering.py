"""Deterministic Korean fallback and ward-risk Markdown rendering."""

from ax_contracts import WardWeeklyMetrics, WardWeeklyReport

from .models import KoreanNarrative


def build_fallback_narrative(metrics: WardWeeklyMetrics) -> KoreanNarrative:
    current = metrics.current.danger_days
    delta = metrics.delta.danger_days
    if current == 0:
        summary = "이번 주에는 위험 감지일이 확인되지 않았습니다. 현재 관찰 흐름을 유지할 수 있습니다."
    elif delta > 0:
        summary = "지난주보다 위험 감지일이 늘어 최근 감지 내역을 우선 확인할 필요가 있습니다."
    elif delta < 0:
        summary = "위험 감지일은 지난주보다 줄었지만 최근 감지 원인을 계속 확인할 필요가 있습니다."
    else:
        summary = "위험 감지일이 지난주와 같은 수준으로 이어져 반복 원인을 확인할 필요가 있습니다."

    suggestions = [
        "최근 위험 감지 시점의 환경과 활동 기록을 함께 확인하세요.",
        "필요한 후속 확인이 완료되었는지 담당 기록을 점검하세요.",
    ]
    if current == 0:
        suggestions = [
            "현재의 관찰 기준과 점검 주기를 유지하세요.",
            "새로운 변화가 있는지 다음 관찰 기록과 비교하세요.",
        ]
    return KoreanNarrative(summary=summary, suggestions=suggestions)


def render_report(
    metrics: WardWeeklyMetrics,
    narrative: KoreanNarrative,
    generation_mode: str,
) -> WardWeeklyReport:
    mode_label = (
        "AI 기반 서술"
        if generation_mode == "llm"
        else "규칙 기반 대체 문안 — AI 서술을 사용할 수 없어 자동 대체됨"
    )
    suggestions = "\n".join(
        f"- {suggestion}" for suggestion in narrative.suggestions
    )
    markdown = f"""# {metrics.display_name} 주간 위험 리포트

- 기간: {metrics.week_start.isoformat()} ~ {metrics.week_end.isoformat()} (종료일 제외)
- 생성 방식: {mode_label}
- 데이터 기준: 일별 위험 감지 기록

## 핵심 지표

| 지표 | 이번 주 | 지난 주 | 변화 |
| --- | ---: | ---: | ---: |
| 위험 감지일 | {metrics.current.danger_days}일 | {metrics.previous.danger_days}일 | {_signed(metrics.delta.danger_days, "일")} |

## 이번 주 요약

{narrative.summary}

## 다음 주 제안

{suggestions}
"""
    return WardWeeklyReport(
        ward_id=metrics.ward_id,
        display_name=metrics.display_name,
        metrics=metrics,
        markdown=markdown,
        generation_mode=generation_mode,
    )


def _signed(value: int, unit: str) -> str:
    return f"{value:+d}{unit}"
