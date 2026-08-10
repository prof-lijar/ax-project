"""Compiled graph for one LLM-backed chat turn."""

from langgraph.graph import END, START, StateGraph

from workflows.chat.nodes import generate_response
from workflows.chat.state import ChatState

_builder = StateGraph(ChatState)
_builder.add_node("generate_response", generate_response)
_builder.add_edge(START, "generate_response")
_builder.add_edge("generate_response", END)
graph = _builder.compile()
