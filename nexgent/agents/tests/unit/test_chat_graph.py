from collections.abc import Sequence

import pytest
from ax_integrations import ChatMessage

from workflows.chat import graph


class FakeChatModel:
    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> str:
        assert messages == [{"role": "user", "content": "hello"}]
        assert max_tokens == 500
        assert temperature == 0.7
        return "model response"


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
@pytest.mark.parametrize("value", ["", "   ", None, 42])
async def test_chat_graph_rejects_invalid_message(value: object) -> None:
    with pytest.raises(ValueError, match="message must be a non-empty string"):
        await graph.ainvoke({"message": value})  # type: ignore[typeddict-item]
