import json
from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import APIRouter, File, Form, Request, UploadFile
from starlette.responses import StreamingResponse

from app.chat.agent_server import AgentServerStream, open_agent_stream
from app.chat.attachments import ArtifactBatch, AttachmentProcessor
from app.chat.config import get_chat_settings
from app.chat.errors import ChatRequestError
from app.chat.models import ChatErrorDetail, ChatErrorResponse

router = APIRouter()


@router.post(
    "/stream",
    response_class=StreamingResponse,
    responses={
        400: {"model": ChatErrorResponse},
        413: {"model": ChatErrorResponse},
        415: {"model": ChatErrorResponse},
        502: {"model": ChatErrorResponse},
        503: {"model": ChatErrorResponse},
    },
)
async def stream_chat(
    request: Request,
    prompt: Annotated[str | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> StreamingResponse:
    normalized_prompt = (prompt or "").strip()
    if not normalized_prompt:
        raise ChatRequestError(
            "prompt_required",
            "A non-empty prompt is required.",
        )

    settings = get_chat_settings()
    batch = await AttachmentProcessor(settings).process(files or [])
    try:
        upstream = await open_agent_stream(
            normalized_prompt,
            batch.attachments,
            settings,
        )
    except BaseException:
        await batch.cleanup()
        raise

    return StreamingResponse(
        _relay_stream(upstream, batch),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
        },
    )


async def _relay_stream(
    upstream: AgentServerStream,
    batch: ArtifactBatch,
) -> AsyncIterator[bytes]:
    try:
        async for chunk in upstream.response.aiter_raw():
            yield chunk
    except httpx.HTTPError:
        yield _stream_error_event(
            ChatErrorDetail(
                code="agent_server_stream_error",
                message="The chat stream ended unexpectedly.",
            )
        )
    finally:
        await upstream.close()
        await batch.cleanup()


def _stream_error_event(error: ChatErrorDetail) -> bytes:
    data = json.dumps(
        {"error": error.model_dump(exclude_none=True)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"event: error\ndata: {data}\n\n".encode()
