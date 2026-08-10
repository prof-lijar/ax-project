"""Nodes for the LLM-backed chat workflow."""

from ax_integrations import get_default_chat_model

from .state import ChatState


async def generate_response(state: ChatState) -> ChatState:
    message = state.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string")

    model = get_default_chat_model()
    response = await model.complete(
        [{"role": "user", "content": message.strip()}],
        max_tokens=500,
        temperature=0.7,
    )
    return {"response": response}
