"""Worker-injected graph; intentionally not exposed through generic Chat runs."""

from typing import TypedDict

from ax_contracts.sumin import SuminTask
from langgraph.graph import END, START, StateGraph

from workflows.sumin.service import Sumin


class SuminState(TypedDict, total=False):
    task: dict
    result: str


def build_graph(service: Sumin):
    async def execute(state: SuminState):
        return {"result": await service.run(SuminTask.model_validate(state["task"]))}

    builder = StateGraph(SuminState)
    builder.add_node("execute", execute)
    builder.add_edge(START, "execute")
    builder.add_edge("execute", END)
    return builder.compile()
