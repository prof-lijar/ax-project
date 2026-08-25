"""Dedicated SSE boundary for the grounded RAG Chat agent."""

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from app.chat.agent_server import open_agent_stream
from app.chat.config import get_chat_settings
from app.chat.models import ChatErrorResponse
from app.chat.streaming import relay_agent_stream
from app.rag_chat.models import RagChatRequest

RAG_CHAT_ASSISTANT_ID = "rag_chat"

router = APIRouter()


@router.post(
    "/stream",
    response_class=StreamingResponse,
    responses={
        422: {"description": "Invalid RAG Chat request"},
        502: {"model": ChatErrorResponse},
        503: {"model": ChatErrorResponse},
    },
)
async def stream_rag_chat(payload: RagChatRequest) -> StreamingResponse:
    """Route one text-only question to the registered RAG Chat graph."""

    upstream = await open_agent_stream(
        payload.question,
        (),
        get_chat_settings(),
        assistant_id=RAG_CHAT_ASSISTANT_ID,
    )
    return StreamingResponse(
        relay_agent_stream(upstream),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
        },
    )
