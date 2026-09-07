import hashlib
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from ax_contracts import ChatAttachmentRef
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


class DocumentChatModel:
    supports_vision = False

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        assert messages[0]["role"] == "system"
        assert "untrusted user-provided data" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        content = messages[1]["content"]
        assert isinstance(content, list)
        assert content[0] == {"type": "text", "text": "summarize"}
        assert content[1]["type"] == "text"
        assert "BEGIN UNTRUSTED ATTACHMENT" in content[1]["text"]
        assert "grounded facts" in content[1]["text"]
        yield "summary"


class DisabledVisionChatModel:
    supports_vision = False

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        raise AssertionError("model must not be called when vision is disabled")
        yield ""  # pragma: no cover


class EnabledVisionChatModel:
    supports_vision = True

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        content = messages[1]["content"]
        assert isinstance(content, list)
        assert content[1]["type"] == "text"
        assert "photo.png" in content[1]["text"]
        image_part = content[2]
        assert image_part["type"] == "image_url"
        assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
        yield "description"


def _attachment_ref(
    path: Path,
    data: bytes,
    *,
    kind: str = "document",
    media_type: str = "text/plain",
) -> ChatAttachmentRef:
    return ChatAttachmentRef(
        attachment_id="upload_123",
        filename="notes.txt" if kind == "document" else "photo.png",
        kind=kind,
        media_type=media_type,
        uri=path.as_uri(),
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


@pytest.mark.asyncio
async def test_chat_graph_calls_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


@pytest.mark.asyncio
async def test_chat_graph_builds_document_message_without_persisting_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data = b"grounded facts"
    path = tmp_path / "normalized.txt"
    path.write_bytes(data)
    reference = _attachment_ref(path, data)
    monkeypatch.setenv("AX_CHAT_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "workflows.chat.nodes.get_default_chat_model",
        lambda: DocumentChatModel(),
    )

    result = await graph.ainvoke(
        {"message": "summarize", "attachments": [reference.model_dump(mode="json")]}
    )

    assert result["response"] == "summary"
    assert result["attachments"] == []
    assert reference.uri not in repr(result)
    assert "grounded facts" not in repr(result)
    assert not any(isinstance(value, bytes) for value in result.values())


@pytest.mark.asyncio
async def test_chat_graph_emits_safe_vision_capability_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data = b"normalized-image"
    path = tmp_path / "normalized.png"
    path.write_bytes(data)
    reference = _attachment_ref(
        path,
        data,
        kind="image",
        media_type="image/png",
    )
    monkeypatch.setenv("AX_CHAT_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "workflows.chat.nodes.get_default_chat_model",
        lambda: DisabledVisionChatModel(),
    )

    events = [
        event
        async for event in graph.astream(
            {"message": "describe", "attachments": [reference.model_dump(mode="json")]},
            stream_mode="custom",
        )
    ]

    assert events == [
        {
            "error": {
                "schema_version": "1",
                "code": "vision_not_supported",
                "message": "Image attachments are not supported by the configured model.",
                "filename": "photo.png",
            }
        }
    ]
    assert reference.uri not in repr(events)
    assert "data:image" not in repr(events)

    final_state = await graph.ainvoke(
        {"message": "describe", "attachments": [reference.model_dump(mode="json")]}
    )
    assert final_state["error"] == events[0]["error"]
    assert final_state["attachments"] == []
    assert "response" not in final_state


@pytest.mark.asyncio
async def test_chat_graph_keeps_successful_image_bytes_out_of_events_and_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data = b"normalized-image"
    path = tmp_path / "normalized.png"
    path.write_bytes(data)
    reference = _attachment_ref(
        path,
        data,
        kind="image",
        media_type="image/png",
    )
    monkeypatch.setenv("AX_CHAT_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "workflows.chat.nodes.get_default_chat_model",
        lambda: EnabledVisionChatModel(),
    )

    events = [
        event
        async for event in graph.astream(
            {"message": "describe", "attachments": [reference.model_dump(mode="json")]},
            stream_mode="custom",
        )
    ]

    assert events == [
        {"response_delta": "description"},
        {"response_complete": "description"},
    ]
    assert reference.uri not in repr(events)
    assert "data:image" not in repr(events)

    final_state = await graph.ainvoke(
        {"message": "describe", "attachments": [reference.model_dump(mode="json")]}
    )
    assert final_state["response"] == "description"
    assert final_state["attachments"] == []
    assert not any(isinstance(value, bytes) for value in final_state.values())
