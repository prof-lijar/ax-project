"""Versioned prompt construction for the bounded ward-risk narrative step."""

import json

from ax_contracts import WardWeeklyMetrics

SYSTEM_PROMPT = """당신은 생활 안전 주간 위험 리포트 작성자입니다.
제공된 검증 완료 지표와 방향성만 사용하세요.
계산하거나 새로운 사실, 수치, 진단 또는 목표치를 만들지 마세요.
응답의 문장에는 숫자를 쓰지 마세요.
반드시 다음 JSON 객체만 반환하세요:
{"summary": "한국어 요약", "suggestions": ["한국어 제안", "한국어 제안"]}
summary는 한두 문장, suggestions는 서로 다른 확인 가능한 제안 두세 개로 작성하세요.
마크다운, 코드 펜스, 추가 키 또는 JSON 밖의 설명을 반환하지 마세요."""


def build_narrative_messages(metrics: WardWeeklyMetrics) -> list[dict[str, str]]:
    facts = {
        "관리대상": metrics.display_name,
        "위험감지일_방향": _direction(metrics.delta.danger_days),
        "현재주_위험감지여부": (
            "감지됨" if metrics.current.danger_days else "감지되지 않음"
        ),
        "검증된_지표": metrics.model_dump(mode="json"),
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(facts, ensure_ascii=False, separators=(",", ":")),
        },
    ]


def _direction(delta: int) -> str:
    if delta > 0:
        return "증가"
    if delta < 0:
        return "감소"
    return "유지"
