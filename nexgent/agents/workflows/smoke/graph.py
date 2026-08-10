from langgraph.graph import END, START, StateGraph

from workflows.smoke.nodes import acknowledge
from workflows.smoke.state import SmokeState

_builder = StateGraph(SmokeState)
_builder.add_node("acknowledge", acknowledge)
_builder.add_edge(START, "acknowledge")
_builder.add_edge("acknowledge", END)
graph = _builder.compile()
