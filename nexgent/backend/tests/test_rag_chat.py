import asyncio
import json
from pathlib import Path

import httpx
from app.chat.agent_server import open_agent_stream
from app.chat.config import ChatSettings
from app.chat.streaming import relay_agent_stream


async def _request(app, method: str, path: str, **kwargs) -> httpx.Response:
    from conftest import authenticated_headers
    kwargs["headers"] = {**authenticated_headers(), **kwargs.get("headers", {})}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, **kwargs)


class _FakeResponse:
    async def aiter_raw(self):
        yield b'event: values\ndata: {"response":"grounded"}\n\n'


class _FakeUpstream:
    def __init__(self) -> None:
        self.response = _FakeResponse()
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _settings(tmp_path: Path) -> ChatSettings:
    return ChatSettings(
        agent_server_url="http://agent-server",
        assistant_id="chat",
        artifact_root=tmp_path,
        stale_after_seconds=900,
        connect_timeout_seconds=1,
        write_timeout_seconds=1,
    )


def test_dedicated_rag_chat_route_preserves_question_and_streams(monkeypatch):
    captured = {}
    upstream = _FakeUpstream()

    async def fake_open(prompt, attachments, settings, *, assistant_id=None):
        captured.update(
            prompt=prompt,
            attachments=attachments,
            assistant_id=assistant_id,
            configured_default=settings.assistant_id,
        )
        return upstream

    monkeypatch.setattr("app.rag_chat.router.open_agent_stream", fake_open)
    from conftest import feature_app as create_app

    response = asyncio.run(
        _request(
            create_app(),
            "POST",
            "/api/rag/chat/stream",
            json={"question": "  exact original question  "},
        )
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.content == b'event: values\ndata: {"response":"grounded"}\n\n'
    assert captured == {
        "prompt": "  exact original question  ",
        "attachments": (),
        "assistant_id": "rag_chat",
        "configured_default": "chat",
    }
    assert upstream.closed is True


def test_rag_chat_rejects_blank_and_attachment_like_payloads(monkeypatch):
    async def must_not_open(*_args, **_kwargs):
        raise AssertionError("Agent Server must not be called")

    monkeypatch.setattr("app.rag_chat.router.open_agent_stream", must_not_open)
    from conftest import feature_app as create_app

    blank = asyncio.run(
        _request(
            create_app(),
            "POST",
            "/api/rag/chat/stream",
            json={"question": "   "},
        )
    )
    attachment_like = asyncio.run(
        _request(
            create_app(),
            "POST",
            "/api/rag/chat/stream",
            json={"question": "question", "files": ["not-supported"]},
        )
    )

    assert blank.status_code == 422
    assert attachment_like.status_code == 422


def test_agent_server_override_selects_only_rag_chat_graph(tmp_path):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=b'event: values\ndata: {"response":"done"}\n\n',
        )

    async def exercise():
        stream = await open_agent_stream(
            "question",
            (),
            _settings(tmp_path),
            assistant_id="rag_chat",
            transport=httpx.MockTransport(handler),
        )
        await stream.response.aread()
        await stream.close()

    asyncio.run(exercise())

    assert captured["payload"] == {
        "assistant_id": "rag_chat",
        "input": {"message": "question"},
        "stream_mode": ["custom", "values"],
        "on_disconnect": "cancel",
    }


def test_shared_stream_relay_closes_upstream_and_runs_cleanup():
    upstream = _FakeUpstream()
    cleanup_calls = 0

    async def cleanup() -> None:
        nonlocal cleanup_calls
        cleanup_calls += 1

    async def exercise() -> bytes:
        return b"".join(
            [chunk async for chunk in relay_agent_stream(upstream, cleanup)]
        )

    body = asyncio.run(exercise())

    assert body == b'event: values\ndata: {"response":"grounded"}\n\n'
    assert upstream.closed is True
    assert cleanup_calls == 1


def test_shared_stream_relay_sanitizes_upstream_read_failure():
    class FailingResponse:
        async def aiter_raw(self):
            raise httpx.ReadError("private upstream detail")
            yield b""  # pragma: no cover

    upstream = _FakeUpstream()
    upstream.response = FailingResponse()

    async def exercise() -> bytes:
        return b"".join([chunk async for chunk in relay_agent_stream(upstream)])

    body = asyncio.run(exercise())

    assert b"private upstream detail" not in body
    assert b"agent_server_stream_error" in body
    assert upstream.closed is True
