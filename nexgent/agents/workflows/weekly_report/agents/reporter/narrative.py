"""Model call, one validation retry, and disclosed deterministic fallback."""

from __future__ import annotations

import json
from typing import Any

from ax_contracts import NarrativeGenerationMetadata, WeeklyNarrative
from ax_integrations import ModelRequestError
from pydantic import ValidationError

from workflows.weekly_report.domain.models import FactPackage

from .fallback import build_fallback
from .policy import validate_narrative
from .prompt import PROMPT_VERSION, build_messages


async def generate_narrative(model: Any, facts: FactPackage) -> tuple[
    WeeklyNarrative, str, NarrativeGenerationMetadata
]:
    feedback = None
    last_reason = "model_narrative_unavailable"
    for _ in range(2):
        try:
            response = await model.complete(
                build_messages(facts, feedback), max_tokens=900, temperature=0.2
            )
        except ModelRequestError as exc:
            last_reason = _safe_reason(exc)
            break
        try:
            narrative = _parse(response, facts)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_reason = _safe_reason(exc)
            feedback = _correction_feedback(exc)
            continue
        return narrative, "llm", NarrativeGenerationMetadata(
            prompt_version=PROMPT_VERSION,
            model=_model_name(model),
            validation_status="passed",
        )
    fallback = build_fallback(facts)
    return fallback, "template_fallback", NarrativeGenerationMetadata(
        prompt_version=PROMPT_VERSION,
        model=_model_name(model),
        validation_status="fallback",
        fallback_reason=last_reason,
    )


def _parse(response: str, facts: FactPackage) -> WeeklyNarrative:
    if not response.strip():
        raise ValueError("empty model output")
    return validate_narrative(
        WeeklyNarrative.model_validate_json(_json_document(response)),
        facts.allowed_topics,
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
    if "four to six sentences" in message:
        return "analysis_text를 마침표로 구분된 네 문장부터 여섯 문장으로 다시 작성하세요."
    if "220 to 420 characters" in message:
        return "analysis_text를 이백이십 자부터 사백이십 자로 다시 작성하세요."
    if "must not contain digits" in message:
        return "모든 출력에서 숫자를 제거하고 한글 표현만 사용하세요."
    if "must contain Korean" in message:
        return "모든 문구를 자연스러운 한국어로 작성하세요."
    if "forbidden categorical language" in message:
        return "단정, 진단, 명령 표현을 제거하고 부드러운 관찰과 권유로 바꾸세요."
    if "unsupported topic" in message:
        return "제공된 allowed_topics에 포함된 주제만 언급하세요."
    if "must be unique" in message:
        return "observations와 suggestions에서 중복 문구를 제거하세요."
    return "제공된 출력 규칙을 모두 확인하여 JSON 객체를 다시 작성하세요."
