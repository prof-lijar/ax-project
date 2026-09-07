"""Compiled graph for one grounded RAG chat turn."""

from langgraph.graph import END, START, StateGraph

from workflows.rag_chat.nodes import answer_with_rag
from workflows.rag_chat.state import RagChatState

_builder = StateGraph(RagChatState)
_builder.add_node("answer_with_rag", answer_with_rag)
_builder.add_edge(START, "answer_with_rag")
_builder.add_edge("answer_with_rag", END)
graph = _builder.compile()
