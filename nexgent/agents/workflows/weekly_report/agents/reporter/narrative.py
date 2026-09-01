"""Model call, one validation retry, and disclosed deterministic fallback."""

from __future__ import annotations

import re
from typing import Any

from ax_contracts import NarrativeGenerationMetadata, WeeklyNarrative
from ax_integrations import ModelRequestError

from workflows.weekly_report.domain.models import FactPackage

from .fallback import build_fallback
from .policy import validate_summary_text
from .prompt import PROMPT_VERSION, build_messages


async def generate_narrative(
    model: Any, facts: FactPackage
) -> tuple[WeeklyNarrative, str, NarrativeGenerationMetadata]:
    feedback = None
    last_reason = "model_narrative_unavailable"
    for _ in range(2):
        try:
            response, usage = await _complete(model, facts, feedback)
        except ModelRequestError as exc:
            last_reason = _safe_reason(exc)
            break
        try:
            narrative = _parse(response, facts)
        except ValueError as exc:
            last_reason = _safe_reason(exc)
            feedback = _correction_feedback(exc)
            continue
        return (
            narrative,
            "llm",
            NarrativeGenerationMetadata(
                prompt_version=PROMPT_VERSION,
                model=usage.get("model") or _model_name(model),
                validation_status="passed",
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                latency_ms=usage.get("latency_ms"),
            ),
        )
    fallback = build_fallback(facts)
    return (
        fallback,
        "template_fallback",
        NarrativeGenerationMetadata(
            prompt_version=PROMPT_VERSION,
            model=_model_name(model),
            validation_status="fallback",
            fallback_reason=last_reason,
        ),
    )


async def _complete(
    model: Any, facts: FactPackage, feedback: str | None
) -> tuple[str, dict[str, Any]]:
    messages = build_messages(facts, feedback)
    return await model.complete(messages, max_tokens=600, temperature=0.3), {}


def _parse(response: str, facts: FactPackage) -> WeeklyNarrative:
    summary = validate_summary_text(response, facts)
    sentences = re.split(r"(?<=[.!?])\s+", summary)
    return WeeklyNarrative(
        headline=sentences[0],
        analysis_text=" ".join(sentences[1:]),
        observations=[],
        suggestions=[],
    )


def _model_name(model: Any) -> str | None:
    settings = getattr(model, "settings", None)
    name = getattr(settings, "model", None)
    return str(name)[:256] if name else None


def _safe_reason(exc: Exception) -> str:
    if isinstance(exc, ModelRequestError):
        return "model_request_failed"
    return "invalid_narrative_content"


def _correction_feedback(exc: Exception) -> str:
    """Return bounded, non-sensitive guidance for the single corrective retry."""
    message = str(exc)
    if "one paragraph" in message:
        return "줄바꿈 없이 자연스럽게 이어지는 한 문단으로 작성하세요."
    if "body text only" in message:
        return "제목, 항목명, 글머리표, 설명 없이 총평 본문만 작성하세요."
    if "must not contain digits" in message:
        return "숫자, 점수, 날짜, 횟수, 비율, 온도와 습도 수치를 모두 제거하세요."
    if "forbidden output word" in message:
        return "‘움직임’, ‘리모컨’, ‘위험’, GOOD, CAUTION, RISK를 모두 제거하거나 차분한 생활 언어로 바꾸세요."
    if "unsupported safety reassurance" in message:
        return "제공된 기록을 실제 안전 여부로 확대 해석하지 말고, 근거 없이 안심시키거나 상태를 단정하는 표현을 제거하세요."
    if "alarming wording" in message:
        return "느낌표와 긴급하거나 불안하게 느껴지는 표현을 제거하고, 서두르지 않는 차분한 관찰과 확인 안내로 바꾸세요."
    if "persona-misaligned wording" in message:
        return "멀리 사는 자녀 보호자에게 부모님의 생활을 설명하는 상황에 맞게, 감정적 태도를 지시하거나 ‘확인이 필요해요’라고 판단만 전하지 말고 실제 확인 행동을 자연스럽게 안내하세요. ‘TV 이용 시간’은 ‘TV 이용 등 일상적인 생활 패턴’으로 바꾸세요."
    if "excluded risk-management content" in message:
        return "위험 관리와 별도 확인 기록에 관한 내용은 한주 총평에서 모두 제거하세요."
    if "repeats the same sentence" in message or "repeats the same action" in message:
        return "같은 사실이나 같은 목적의 행동 제안을 반복하지 말고, 관련 내용을 한 문장으로 묶어 한 번만 안내하세요."
    if "contradictory stable close" in message:
        return "살펴볼 생활 변화나 기기 확인 사항이 있으므로 일반적인 안심 문구를 제거하고, 제공된 관련 행동 제안을 중복 없이 반영하세요."
    if "known subscriber name" in message:
        return "제공된 가입자 이름을 첫 문장에 정확히 포함하세요."
    if "generic subscriber reference" in message:
        return "가입자를 다시 지칭할 때 일반 호칭 대신 제공된 실제 이름을 사용하세요."
    if "no-reception two-sentence copy" in message:
        return "전체 생활 정보 수신이 없으므로 가입자 이름을 포함해 ‘생활 정보가 들어오지 않은 날이 있었어요. 기기 전원이 잘 연결되어 있는지 확인해 주세요.’의 두 문장으로만 작성하세요."
    if "unsupported no-reception assessment" in message:
        return "전체 생활 정보 수신이 없으므로 다른 생활 상태나 환경을 평가하지 말고 생활 정보 수신과 기기 전원 확인만 안내하세요."
    if "consolidate actions in the closing" in message:
        return "보호자가 확인할 내용을 중복 없이 하나의 마지막 문장으로 합치세요."
    if "facts after the closing action" in message:
        return "생활 변화, 실내 환경, 기기 상태를 먼저 설명하고 보호자가 확인할 내용을 마지막 문장에 배치하세요. 행동 안내 뒤에는 새로운 사실을 덧붙이지 마세요."
    if "grounded closing action" in message:
        return "제공된 행동 제안을 바탕으로 보호자가 확인할 내용을 마지막 한 문장에 자연스럽게 작성하세요."
    if "choppy section recital" in message:
        return "한 가지 사실만 담은 짧은 문장을 연달아 나열하지 말고, 관련된 생활 활동과 생활 패턴, 실내 환경과 기기 상태를 연결 표현으로 묶어 네 문장 이내로 작성하세요."
    if "required opening format" in message:
        return "첫 문장을 반드시 ‘지난 한 주 [제공된 가입자 이름]님은’으로 시작하세요."
    if "repeats the topic particle" in message:
        return "첫 문장의 ‘[이름]님은’ 바로 뒤에 ‘활동은’이나 ‘생활 패턴은’을 이어 쓰지 마세요. ‘활동이’ 또는 ‘TV 이용 등 일상적인 생활 패턴이’처럼 이/가 조사를 사용해 자연스럽게 고치세요."
    if "core lifestyle flow" in message:
        return "첫 문장에 활동과 TV 이용 등 일상적인 생활 패턴에서 확인된 핵심 흐름을 자연스럽게 담으세요."
    if "one to twelve sentences" in message:
        return "마침표로 구분되는 짧은 문장을 한 문단으로 작성하세요."
    if "first sentence" in message:
        return "첫 문장을 더 짧고 자연스럽게 다시 작성하세요."
    if "material section" in message:
        return "살펴볼 생활 활동, 생활 패턴, 실내 환경 또는 기기 상태를 빠뜨리지 말고 자연스럽게 포함하세요."
    if "at most 500 characters" in message:
        return "총평을 오백 자 이내의 짧은 한 문단으로 다시 작성하세요."
    if "urgent wording" in message:
        return (
            "빠른, 즉시, 위급, 긴급 같은 표현을 제거하고 차분한 확인 안내로 바꾸세요."
        )
    if "must contain Korean" in message:
        return "모든 문구를 자연스러운 한국어로 작성하세요."
    if "forbidden categorical language" in message:
        return "단정, 진단, 명령 표현을 제거하고 부드러운 관찰과 권유로 바꾸세요."
    if "unrelated filler" in message:
        return "사과, 근거 없는 안심, 다음 주 약속, 보호자 안부 같은 채움 문구를 제거하고 제공된 facts만 작성하세요."
    if "legacy report-period phrase" in message:
        return "보고 기간은 ‘지난 한 주’, 비교 기간은 ‘2주 전’으로 바꾸고 ‘이번 주’, ‘지난주’, ‘지난 주’는 제거하세요."
    if "warm haeyo register" in message:
        return "딱딱한 합니다체를 존중하는 높임말과 부드러운 해요체로 바꾸세요."
    if "report-excluded topic" in message:
        return "수면과 출동 관련 내용을 모두 제거하고 제공된 보고 영역만 작성하세요."
    if "required topic" in message:
        return "required_topics에 포함된 중요한 이슈를 analysis_text에서 빠짐없이 언급하세요."
    return "제공된 데이터와 출력 규칙을 다시 확인해 총평 본문만 작성하세요."
