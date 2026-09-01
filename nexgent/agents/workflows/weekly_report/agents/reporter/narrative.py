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
        return "‘움직임’, ‘리모컨’, GOOD, CAUTION, RISK를 모두 제거하거나 자연스러운 생활 언어로 바꾸세요."
    if "one to twelve sentences" in message:
        return "마침표로 구분되는 짧은 문장을 한 문단으로 작성하세요."
    if "first sentence" in message:
        return "첫 문장을 더 짧고 자연스럽게 다시 작성하세요."
    if "material section" in message:
        return "주의가 필요한 생활 활동, 생활 패턴, 실내 환경 또는 기기 상태를 빠뜨리지 말고 자연스럽게 포함하세요."
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
