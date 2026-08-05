from langgraph.graph import END, START, StateGraph

from .nodes import acknowledge
from .state import SmokeState

_builder = StateGraph(SmokeState)
_builder.add_node("acknowledge", acknowledge)
_builder.add_edge(START, "acknowledge")
_builder.add_edge("acknowledge", END)
graph = _builder.compile()
