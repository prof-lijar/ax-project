"""Deterministic Korean fallback and Markdown rendering."""

from ax_contracts import UserWeeklyMetrics, UserWeeklyReport

from .models import KoreanNarrative


def build_fallback_narrative(metrics: UserWeeklyMetrics) -> KoreanNarrative:
    completion_delta = metrics.delta.completion_rate_percentage_points
    if metrics.current.assigned_tasks == 0:
        summary = "이번 주에는 기록된 배정 업무가 없어 업무 흐름을 판단하기 어렵습니다."
    elif completion_delta > 0:
        summary = "지난주보다 업무 완료 흐름이 개선되어 안정적인 진전이 확인됩니다."
    elif completion_delta < 0:
        summary = "업무 완료 흐름이 지난주보다 낮아져 우선순위와 방해 요인을 점검할 필요가 있습니다."
    else:
        summary = "업무 완료 흐름이 지난주와 비슷한 수준으로 유지되었습니다."

    suggestions: list[str] = []
    if metrics.current.blockers_opened > metrics.current.blockers_resolved:
        suggestions.append(
            "남아 있는 블로커의 담당자와 해소 조건을 먼저 명확히 하세요."
        )
    if metrics.delta.focus_minutes < 0:
        suggestions.append("집중 업무 시간을 방해하는 일정과 알림을 정리해 보세요.")
    if completion_delta < 0:
        suggestions.append(
            "진행 중인 업무의 우선순위를 다시 확인하고 범위를 조정하세요."
        )
    if completion_delta >= 0:
        suggestions.append(
            "현재의 업무 완료 흐름을 유지할 수 있는 습관을 기록해 보세요."
        )
    if len(suggestions) < 2:
        suggestions.append(
            "다음 주에 가장 중요한 업무와 예상 방해 요인을 미리 정리하세요."
        )
    return KoreanNarrative(summary=summary, suggestions=suggestions[:3])


def render_report(
    metrics: UserWeeklyMetrics,
    narrative: KoreanNarrative,
    generation_mode: str,
) -> UserWeeklyReport:
    mode_label = (
        "AI 기반 서술"
        if generation_mode == "llm"
        else "규칙 기반 대체 문안 — AI 서술을 사용할 수 없어 자동 대체됨"
    )
    current = metrics.current
    previous = metrics.previous
    delta = metrics.delta
    suggestions = "\n".join(f"- {suggestion}" for suggestion in narrative.suggestions)
    markdown = f"""# {metrics.display_name}님의 주간 업무 리포트

- 기간: {metrics.week_start.isoformat()} ~ {metrics.week_end.isoformat()} (종료일 제외)
- 생성 방식: {mode_label}

## 핵심 지표

| 지표 | 이번 주 | 지난 주 | 변화 |
| --- | ---: | ---: | ---: |
| 배정 업무 | {current.assigned_tasks}건 | {previous.assigned_tasks}건 | {_signed(delta.assigned_tasks, "건")} |
| 완료 업무 | {current.completed_tasks}건 | {previous.completed_tasks}건 | {_signed(delta.completed_tasks, "건")} |
| 완료율 | {current.completion_rate_percent:.1f}% | {previous.completion_rate_percent:.1f}% | {_signed(delta.completion_rate_percentage_points, "%p", one_decimal=True)} |
| 집중 시간 | {_duration(current.focus_minutes)} | {_duration(previous.focus_minutes)} | {_signed(delta.focus_minutes, "분")} |
| 활동일 | {current.active_days}일 | {previous.active_days}일 | {_signed(delta.active_days, "일")} |
| 새 블로커 | {current.blockers_opened}건 | {previous.blockers_opened}건 | {_signed(delta.blockers_opened, "건")} |
| 해결 블로커 | {current.blockers_resolved}건 | {previous.blockers_resolved}건 | {_signed(delta.blockers_resolved, "건")} |

## 이번 주 요약

{narrative.summary}

## 다음 주 제안

{suggestions}
"""
    return UserWeeklyReport(
        user_id=metrics.user_id,
        display_name=metrics.display_name,
        metrics=metrics,
        markdown=markdown,
        generation_mode=generation_mode,
    )


def _duration(minutes: int) -> str:
    hours, remainder = divmod(minutes, 60)
    return f"{hours}시간 {remainder}분"


def _signed(value: float, unit: str, *, one_decimal: bool = False) -> str:
    rendered = f"{value:+.1f}" if one_decimal else f"{int(value):+d}"
    return f"{rendered}{unit}"
