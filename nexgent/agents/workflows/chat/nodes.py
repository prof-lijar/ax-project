"""Nodes for the LLM-backed chat workflow."""

from ax_integrations import ModelRequestError, get_default_chat_model
from langgraph.config import get_stream_writer

from .state import ChatState

MAX_RESPONSE_TOKENS = 2_048


async def generate_response(state: ChatState) -> ChatState:
    message = state.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string")

    model = get_default_chat_model()
    stream_writer = get_stream_writer()
    chunks: list[str] = []
    async for chunk in model.stream(
        [{"role": "user", "content": message.strip()}],
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
    return {"response": response}
