from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class SmokeState(TypedDict, total=False):
    message: str
    response: str


def acknowledge(state: SmokeState) -> SmokeState:
    message = state.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string")
    return {"response": f"ack: {message.strip()}"}


_builder = StateGraph(SmokeState)
_builder.add_node("acknowledge", acknowledge)
_builder.add_edge(START, "acknowledge")
_builder.add_edge("acknowledge", END)
graph = _builder.compile()
