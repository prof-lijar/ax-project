import asyncio

import pytest
from ax_integrations import ModelRequestError
from langgraph.checkpoint.memory import InMemorySaver

from workflows.chat.graph import _builder
from workflows.chat.memory import (
    MAX_HISTORY_CHARACTERS,
    MAX_HISTORY_TURNS,
    bounded_history,
)


class RecordingModel:
    supports_vision = False

    def __init__(self):
        self.calls = []
        self.fail = False
        self.block = False
        self.started = asyncio.Event()

    async def stream(self, messages, **kwargs):
        self.calls.append(messages)
        self.started.set()
        yield "remembered"
        if self.fail:
            raise ModelRequestError("temporary failure", retryable=True)
        if self.block:
            await asyncio.Event().wait()


@pytest.fixture
def model(monkeypatch):
    model = RecordingModel()
    monkeypatch.setattr("workflows.chat.nodes.get_default_chat_model", lambda: model)
    return model


@pytest.mark.asyncio
async def test_followup_remembers_only_its_thread_after_graph_recreation(model):
    saver = InMemorySaver()
    graph = _builder.compile(checkpointer=saver)
    config = {"configurable": {"thread_id": "one"}}
    await graph.ainvoke({"message": "My name is Mina"}, config)
    # Recompile to prove memory belongs to checkpoints, not a node/process global.
    graph = _builder.compile(checkpointer=saver)
    await graph.ainvoke({"message": "What is my name?"}, config)
    assert model.calls[-1] == [
        {"role": "user", "content": "My name is Mina"},
        {"role": "assistant", "content": "remembered"},
        {"role": "user", "content": "What is my name?"},
    ]
    await graph.ainvoke(
        {"message": "Who am I?"}, {"configurable": {"thread_id": "two"}}
    )
    assert model.calls[-1] == [{"role": "user", "content": "Who am I?"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_failed_or_cancelled_turn_never_enters_history(model, cancel):
    graph = _builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "one"}}
    await graph.ainvoke({"message": "Keep this"}, config)
    model.fail = not cancel
    model.block = cancel
    model.started.clear()
    task = asyncio.create_task(graph.ainvoke({"message": "Incomplete"}, config))
    await model.started.wait()
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else ModelRequestError):
        await task
    snapshot = await graph.aget_state(config)
    assert snapshot.values["history"] == [
        {"user": "Keep this", "assistant": "remembered"}
    ]
    model.fail = model.block = False
    await graph.ainvoke(
        {"message": "Continue", "attachments": [], "response": "", "error": None},
        config,
    )
    assert model.calls[-1] == [
        {"role": "user", "content": "Keep this"},
        {"role": "assistant", "content": "remembered"},
        {"role": "user", "content": "Continue"},
    ]


@pytest.mark.asyncio
async def test_custom_only_stream_completes_without_exposing_history(model):
    graph = _builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "one"}}
    await graph.ainvoke({"message": "Earlier private message"}, config)
    events = [
        event
        async for event in graph.astream(
            {"message": "Follow up"}, config, stream_mode="custom"
        )
    ]
    assert events == [
        {"response_delta": "remembered"},
        {"response_complete": "remembered"},
    ]


def test_history_limits_preserve_whole_recent_turns():
    turns = [{"user": str(i), "assistant": "answer"} for i in range(25)]
    assert bounded_history(turns) == turns[-MAX_HISTORY_TURNS:]
    large = {"user": "u" * (MAX_HISTORY_CHARACTERS // 2), "assistant": "a"}
    assert bounded_history([large, large, turns[-1]]) == [large, turns[-1]]
    assert (
        bounded_history(
            [turns[0], {"user": "x" * MAX_HISTORY_CHARACTERS, "assistant": "a"}]
        )
        == []
    )


@pytest.mark.asyncio
async def test_checkpoint_history_remains_bounded_over_many_turns(model):
    graph = _builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "one"}}
    for i in range(MAX_HISTORY_TURNS + 3):
        result = await graph.ainvoke({"message": f"Turn {i}"}, config)
    assert len(result["history"]) == MAX_HISTORY_TURNS
    assert result["history"][0]["user"] == "Turn 3"
    assert len(model.calls[-1]) == MAX_HISTORY_TURNS * 2 + 1
