from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Request, UploadFile
from starlette.responses import StreamingResponse

from app.chat.models import ChatErrorResponse
from app.chat.history_router import legacy_stream

router = APIRouter()


@router.post(
    "/stream",
    response_class=StreamingResponse,
    responses={
        400: {"model": ChatErrorResponse},
        409: {"model": ChatErrorResponse},
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
    session_id: Annotated[UUID | None, Form()] = None,
) -> StreamingResponse:
    return await legacy_stream(request, prompt, files, session_id)
