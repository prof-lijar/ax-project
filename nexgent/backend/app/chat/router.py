from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from starlette.responses import StreamingResponse

from app.chat.agent_server import open_agent_stream
from app.chat.attachments import AttachmentProcessor
from app.chat.config import get_chat_settings
from app.chat.errors import ChatRequestError
from app.chat.models import ChatErrorResponse
from app.chat.streaming import relay_agent_stream

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
        relay_agent_stream(upstream, batch.cleanup),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
        },
    )
