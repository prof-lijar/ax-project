"""Shared safe relay for Agent Server SSE streams."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx

from app.chat.agent_server import AgentServerStream
from app.chat.models import ChatErrorDetail

AsyncCleanup = Callable[[], Awaitable[None]]


async def relay_agent_stream(
    upstream: AgentServerStream,
    cleanup: AsyncCleanup | None = None,
) -> AsyncIterator[bytes]:
    try:
        async for chunk in upstream.response.aiter_raw():
            yield chunk
    except httpx.HTTPError:
        yield stream_error_event(
            ChatErrorDetail(
                code="agent_server_stream_error",
                message="The chat stream ended unexpectedly.",
            )
        )
    finally:
        await upstream.close()
        if cleanup is not None:
            await cleanup()


def stream_error_event(error: ChatErrorDetail) -> bytes:
    data = json.dumps(
        {"error": error.model_dump(exclude_none=True)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"event: error\ndata: {data}\n\n".encode()
