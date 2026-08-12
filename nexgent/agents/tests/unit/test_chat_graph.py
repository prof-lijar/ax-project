from collections.abc import AsyncIterator, Sequence

import pytest
from ax_integrations import ChatMessage, ModelRequestError

from workflows.chat import graph


class FakeChatModel:
    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        assert messages == [{"role": "user", "content": "hello"}]
        assert max_tokens == 2_048
        assert temperature == 0.7
        yield "model"
        yield " response"


class EmptyChatModel:
    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        if False:
            yield ""


@pytest.mark.asyncio
async def test_chat_graph_calls_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "workflows.chat.nodes.get_default_chat_model",
        lambda: FakeChatModel(),
    )

    assert await graph.ainvoke({"message": " hello "}) == {
        "message": " hello ",
        "response": "model response",
    }


@pytest.mark.asyncio
async def test_chat_graph_emits_safe_response_deltas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "workflows.chat.nodes.get_default_chat_model",
        lambda: FakeChatModel(),
    )

    events = [
        event
        async for event in graph.astream(
            {"message": " hello "},
            stream_mode=["custom", "values"],
        )
    ]

    assert [data for mode, data in events if mode == "custom"] == [
        {"response_delta": "model"},
        {"response_delta": " response"},
    ]
    assert [data for mode, data in events if mode == "values"][-1] == {
        "message": " hello ",
        "response": "model response",
    }


@pytest.mark.asyncio
async def test_chat_graph_rejects_empty_model_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "workflows.chat.nodes.get_default_chat_model",
        lambda: EmptyChatModel(),
    )

    with pytest.raises(ModelRequestError, match="empty response"):
        await graph.ainvoke({"message": "hello"})


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["", "   ", None, 42])
async def test_chat_graph_rejects_invalid_message(value: object) -> None:
    with pytest.raises(ValueError, match="message must be a non-empty string"):
        await graph.ainvoke({"message": value})  # type: ignore[typeddict-item]
