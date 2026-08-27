"""Model call, one validation retry, and disclosed deterministic fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from ax_contracts import NarrativeGenerationMetadata, WeeklyNarrative
from ax_integrations import ModelRequestError
from pydantic import ValidationError

from workflows.weekly_report.domain.models import FactPackage

from .fallback import build_fallback
from .policy import validate_narrative
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
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
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
    structured = getattr(model, "complete_structured", None)
    if structured is None:
        return await model.complete(messages, max_tokens=900, temperature=0.2), {}
    result = await structured(
        messages,
        response_schema=WeeklyNarrative.model_json_schema(),
        schema_name="weekly_narrative",
        max_tokens=900,
        temperature=0.2,
    )
    return result.text, {
        "model": result.model,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "latency_ms": result.latency_ms,
    }


def _parse(response: str, facts: FactPackage) -> WeeklyNarrative:
    if not response.strip():
        raise ValueError("empty model output")
    narrative = WeeklyNarrative.model_validate_json(_json_document(response))
    if (
        facts.summary_outline is not None
        and narrative.headline != facts.summary_outline.headline
    ):
        raise ValueError("headline must match the personalized summary outline")
    return validate_narrative(
        narrative,
        facts.allowed_topics,
        facts.required_topics,
        set(
            re.findall(
                r"\d+(?:[.,]\d+)?",
                " ".join(facts.facts).replace("2주 전", ""),
            )
        ),
        facts.summary_outline is not None,
        (
            facts.summary_outline.available_item_list
            if facts.summary_outline is not None
            else None
        ),
    )


def _json_document(response: str) -> str:
    """Unwrap one complete JSON code fence without extracting surrounding prose."""
    stripped = response.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if (
        len(lines) < 3
        or lines[0].strip().lower() not in {"```", "```json"}
        or lines[-1].strip() != "```"
    ):
        raise ValueError("model output has an invalid JSON code fence")
    document = "\n".join(lines[1:-1]).strip()
    if not document:
        raise ValueError("model output JSON code fence is empty")
    return document


def _model_name(model: Any) -> str | None:
    settings = getattr(model, "settings", None)
    name = getattr(settings, "model", None)
    return str(name)[:256] if name else None


def _safe_reason(exc: Exception) -> str:
    if isinstance(exc, ModelRequestError):
        return "model_request_failed"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    if isinstance(exc, ValidationError):
        return "invalid_narrative_schema"
    return "invalid_narrative_content"


def _correction_feedback(exc: Exception) -> str:
    """Return bounded, non-sensitive guidance for the single corrective retry."""
    if isinstance(exc, json.JSONDecodeError):
        return "코드 블록이나 설명 없이 지정된 필드의 JSON 객체만 반환하세요."
    if isinstance(exc, ValidationError):
        error_types = {item["type"] for item in exc.errors(include_input=False)}
        if "json_invalid" in error_types:
            return "코드 블록이나 설명 없이 올바른 JSON 객체만 반환하세요."
        return "headline, analysis_text, observations, suggestions 필드와 타입을 정확히 맞추세요."

    message = str(exc)
    if "one to four insights" in message:
        return "평가 가능한 핵심 통찰만 한 문장부터 네 문장으로 간결하게 다시 작성하세요."
    if "one to six sentences" in message:
        return (
            "analysis_text를 마침표로 구분된 한 문장부터 여섯 문장으로 다시 작성하세요."
        )
    if "observations must match insight availability" in message:
        return "평가 가능한 통찰이 없으면 observations를 빈 배열로, 있으면 핵심 관찰만 한 개부터 세 개로 작성하세요."
    if "at most 420 characters" in message:
        return "analysis_text를 사백이십 자 이내로 다시 작성하세요."
    if "structured summary must contain at most 450" in message:
        return "headline과 analysis_text를 합쳐 사백오십 자 이내로 간결하게 다시 작성하세요."
    if "repeats a connector" in message:
        return "같은 연결어를 반복하지 말고 선택한 핵심 통찰을 자연스럽게 이어 주세요."
    if "must use connectors" in message:
        return "analysis_text의 첫 문장부터 자연스러운 연결어를 사용해 headline과 이어지도록 다시 작성하세요."
    if "headline must start with the report period" in message:
        return "headline은 ‘지난 한 주’로 시작하고 가입자 이름이 포함된 summary_outline.headline을 그대로 사용하세요."
    if "analysis repeats the report period" in message:
        return "‘지난 한 주’는 headline에만 한 번 두고 analysis_text에서는 반복하지 마세요."
    if "urgent wording" in message:
        return "빠른, 즉시, 위급, 긴급 같은 표현을 제거하고 차분한 확인 안내로 바꾸세요."
    if "repeats a sentence ending" in message:
        return "같은 종결어를 세 번 이상 반복하지 말고 문장 끝맺음을 자연스럽게 바꿔 주세요."
    if "unsupported digits" in message:
        return "summary_outline에 제공된 의미 있는 횟수와 일수 외의 숫자를 모두 제거하세요."
    if "must contain Korean" in message:
        return "모든 문구를 자연스러운 한국어로 작성하세요."
    if "forbidden categorical language" in message:
        return "단정, 진단, 명령 표현을 제거하고 부드러운 관찰과 권유로 바꾸세요."
    if "unrelated filler" in message:
        return "사과, 근거 없는 안심, 다음 주 약속, 보호자 안부 같은 채움 문구를 제거하고 제공된 facts만 작성하세요."
    if "legacy report-period phrase" in message:
        return "보고 기간은 ‘지난 한 주’, 비교 기간은 ‘2주 전’으로 바꾸고 ‘이번 주’, ‘지난주’, ‘지난 주’는 제거하세요."
    if "headline must match" in message:
        return "summary_outline.headline을 한 글자도 바꾸지 말고 headline에 그대로 사용하세요."
    if "omitted item" in message:
        return "omitted_item_list의 항목을 모두 제거하고 available_item_list에 있는 항목만 작성하세요."
    if "formal Korean register" in message:
        return "headline과 analysis_text의 해요체를 제거하고 따뜻하고 정중한 합니다체로 다시 작성하세요."
    if "unsupported topic" in message:
        return "제공된 allowed_topics에 포함된 주제만 언급하세요."
    if "report-excluded topic" in message:
        return "수면과 출동 관련 내용을 모두 제거하고 제공된 보고 영역만 작성하세요."
    if "required topic" in message:
        return "required_topics에 포함된 중요한 이슈를 analysis_text에서 빠짐없이 언급하세요."
    if "must be unique" in message:
        return "observations와 suggestions에서 중복 문구를 제거하세요."
    return "제공된 출력 규칙을 모두 확인하여 JSON 객체를 다시 작성하세요."
