"""Retrieve evidence and generate one grounded RAG answer."""

from __future__ import annotations

from ax_integrations import (
    DEFAULT_RAG_TOP_K,
    ModelConfigurationError,
    ModelRequestError,
    RagSearchConfigurationError,
    RagSearchError,
    get_default_chat_model,
    get_default_rag_search_client,
)
from langgraph.config import get_stream_writer

from .prompt import (
    INSUFFICIENT_CONTEXT_RESPONSE,
    build_rag_messages,
    format_sources,
)
from .state import RagChatState

MAX_RESPONSE_TOKENS = 2_048
RAG_RESPONSE_TEMPERATURE = 0.2


def _safe_error_result(code: str, message: str) -> RagChatState:
    payload = {"schema_version": "1", "code": code, "message": message}
    get_stream_writer()({"error": payload})
    return {"error": payload}  # type: ignore[typeddict-item]


async def answer_with_rag(state: RagChatState) -> RagChatState:
    """Use exact vector retrieval, then the configured chat model when evidence exists."""

    question = state.get("message")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("message must be a non-empty string")

    try:
        retrieval = await get_default_rag_search_client().search(
            question,
            top_k=DEFAULT_RAG_TOP_K,
        )
    except (RagSearchConfigurationError, RagSearchError):
        return _safe_error_result(
            "rag_retrieval_unavailable",
            "RAG retrieval is temporarily unavailable.",
        )

    stream_writer = get_stream_writer()
    if not retrieval.results:
        stream_writer({"response_delta": INSUFFICIENT_CONTEXT_RESPONSE})
        return {"response": INSUFFICIENT_CONTEXT_RESPONSE}

    messages = build_rag_messages(question, retrieval.results)
    chunks: list[str] = []
    try:
        model = get_default_chat_model()
        async for chunk in model.stream(
            messages,
            max_tokens=MAX_RESPONSE_TOKENS,
            temperature=RAG_RESPONSE_TEMPERATURE,
        ):
            if not chunk:
                continue
            chunks.append(chunk)
            stream_writer({"response_delta": chunk})
    except (ModelConfigurationError, ModelRequestError):
        return _safe_error_result(
            "rag_generation_unavailable",
            "The grounded answer service is temporarily unavailable.",
        )

    answer = "".join(chunks).strip()
    if not answer:
        return _safe_error_result(
            "rag_generation_unavailable",
            "The grounded answer service returned an empty response.",
        )

    source_appendix = "\n\n" + format_sources(retrieval.results)
    stream_writer({"response_delta": source_appendix})
    return {"response": answer + source_appendix}
