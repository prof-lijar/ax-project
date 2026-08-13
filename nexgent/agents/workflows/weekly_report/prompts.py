"""Versioned prompt construction for the bounded narrative step."""

import json

from ax_contracts import UserWeeklyMetrics

SYSTEM_PROMPT = """당신은 개인 주간 업무 리포트 작성자입니다.
제공된 검증 완료 지표와 방향성만 사용하세요.
계산하거나 새로운 사실, 수치, 목표치를 만들지 마세요.
응답의 문장에는 숫자를 쓰지 마세요.
반드시 다음 JSON 객체만 반환하세요:
{"summary": "한국어 요약", "suggestions": ["한국어 제안", "한국어 제안"]}
summary는 한두 문장, suggestions는 서로 다른 실행 가능한 제안 두세 개로 작성하세요.
마크다운, 코드 펜스, 추가 키 또는 JSON 밖의 설명을 반환하지 마세요."""


def build_narrative_messages(metrics: UserWeeklyMetrics) -> list[dict[str, str]]:
    facts = {
        "사용자": metrics.display_name,
        "완료율_방향": _direction(metrics.delta.completion_rate_percentage_points),
        "집중시간_방향": _direction(metrics.delta.focus_minutes),
        "활동일_방향": _direction(metrics.delta.active_days),
        "블로커_상태": _blocker_state(metrics),
        "검증된_지표": metrics.model_dump(mode="json"),
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(facts, ensure_ascii=False, separators=(",", ":")),
        },
    ]


def _direction(delta: float) -> str:
    if delta > 0:
        return "상승"
    if delta < 0:
        return "하락"
    return "유지"


def _blocker_state(metrics: UserWeeklyMetrics) -> str:
    difference = metrics.current.blockers_opened - metrics.current.blockers_resolved
    if difference > 0:
        return "새로 열린 블로커가 해결된 블로커보다 많음"
    if difference < 0:
        return "해결된 블로커가 새로 열린 블로커보다 많음"
    return "새로 열린 블로커와 해결된 블로커가 균형을 이룸"
