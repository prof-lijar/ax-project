"""Versioned, spreadsheet-inspired prompt built from qualitative facts only."""

import json

from ax_integrations import ChatMessage

from workflows.weekly_report.domain.models import FactPackage

PROMPT_VERSION = "weekly-korean-warm-v2"


def build_messages(facts: FactPackage, feedback: str | None = None) -> list[ChatMessage]:
    system = """당신은 보호자와 돌봄 담당자를 위한 주간 생활 요약 작성자입니다.
제공된 정성 사실만 사용하고, 따뜻하고 차분하며 사람다운 한국어로 작성하세요.
과도한 확신, 불안 조장, 진단, 원인 추정, 사고나 응급 상황의 단정은 금지합니다.
출동 사유를 추정하지 말고, 자료 부족은 건강 상태와 분리해서 설명하세요.
명령 대신 부드러운 권유를 사용하세요. 출력 문구에는 숫자를 쓰지 마세요.
analysis_text는 네 문장부터 여섯 문장, 이백이십 자부터 사백이십 자로 작성하세요.
각 문장은 마침표, 느낌표, 물음표 중 하나로 끝내고 다음 문장과 공백으로 구분하세요.
제출 전에 analysis_text의 문장 수와 글자 수를 확인하세요.
JSON 객체만 반환하세요: headline, analysis_text, observations, suggestions.
observations는 한 개부터 세 개, suggestions는 최대 세 개입니다."""
    payload = {
        "facts": facts.facts,
        "allowed_topics": facts.allowed_topics,
        "suggested_actions": facts.suggested_actions,
        "coverage": facts.coverage,
    }
    user = "검증된 사실 꾸러미:\n" + json.dumps(payload, ensure_ascii=False)
    if feedback:
        user += "\n이전 출력 검증 오류를 고쳐 다시 작성하세요: " + feedback
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
