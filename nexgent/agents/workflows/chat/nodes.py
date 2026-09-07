"""Nodes for the LLM-backed chat workflow."""

from ax_contracts import ChatAttachmentRef, ChatErrorPayload
from ax_integrations import (
    MAX_ATTACHMENT_COUNT,
    UNTRUSTED_ATTACHMENT_INSTRUCTION,
    AttachmentReadError,
    ChatMessage,
    ModelRequestError,
    get_default_attachment_reader,
    get_default_chat_model,
)
from langgraph.config import get_stream_writer
from pydantic import TypeAdapter, ValidationError

from .state import ChatState

MAX_RESPONSE_TOKENS = 2_048
_ATTACHMENTS_ADAPTER = TypeAdapter(list[ChatAttachmentRef])


def _safe_error_result(error: ChatErrorPayload) -> ChatState:
    error_payload = error.model_dump(mode="json")
    get_stream_writer()({"error": error_payload})
    return {
        "attachments": [],
        "error": error_payload,  # type: ignore[typeddict-item]
    }


def _validate_attachments(value: object) -> list[ChatAttachmentRef]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_ATTACHMENT_COUNT:
        raise AttachmentReadError(
            "attachment_invalid",
            f"At most {MAX_ATTACHMENT_COUNT} attachments are allowed.",
        )
    try:
        attachments = _ATTACHMENTS_ADAPTER.validate_python(value)
    except ValidationError as exc:
        raise AttachmentReadError(
            "attachment_invalid",
            "One or more attachment references are invalid.",
        ) from exc
    attachment_ids = [attachment.attachment_id for attachment in attachments]
    if len(attachment_ids) != len(set(attachment_ids)):
        raise AttachmentReadError(
            "attachment_invalid",
            "Attachment references must be unique.",
        )
    return attachments


async def generate_response(state: ChatState) -> ChatState:
    message = state.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string")

    try:
        attachments = _validate_attachments(state.get("attachments"))
    except AttachmentReadError as exc:
        return _safe_error_result(exc.payload)

    model = get_default_chat_model()
    stream_writer = get_stream_writer()
    messages: list[ChatMessage] = [{"role": "user", "content": message.strip()}]
    if attachments:
        try:
            content = await get_default_attachment_reader().build_user_content(
                message.strip(),
                attachments,
                supports_vision=model.supports_vision,
            )
        except AttachmentReadError as exc:
            return _safe_error_result(exc.payload)
        messages = [
            {"role": "system", "content": UNTRUSTED_ATTACHMENT_INSTRUCTION},
            {"role": "user", "content": content},
        ]

    chunks: list[str] = []
    async for chunk in model.stream(
        messages,
        max_tokens=MAX_RESPONSE_TOKENS,
        temperature=0.7,
    ):
        if not chunk:
            continue
        chunks.append(chunk)
        stream_writer({"response_delta": chunk})

    response = "".join(chunks)
    if not response:
        raise ModelRequestError(
            "model returned an empty response",
            retryable=False,
        )
    if attachments:
        stream_writer({"response_complete": response})
        return {"attachments": [], "response": response}
    return {"response": response}
