import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.chat.attachments import cleanup_stale_artifacts
from app.chat.config import get_chat_settings
from app.chat.errors import ChatRequestError
from app.chat.router import router as chat_router
from app.nextcloud.router import router as nextcloud_router
from app.rag_chat.router import router as rag_chat_router

DEFAULT_DEV_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://192.168.0.18:5173",
    "http://192.168.0.18:5174",
]


def _cors_origins() -> list[str]:
    configured = os.getenv("NEXGENT_CORS_ORIGINS")
    if configured is None:
        return DEFAULT_DEV_ORIGINS
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def _cors_origin_regex() -> str | None:
    configured = os.getenv("NEXGENT_CORS_ORIGIN_REGEX", "").strip()
    if configured:
        return configured

    frontend_port = os.getenv("NEXGENT_CORS_FRONTEND_PORT", "").strip()
    if frontend_port.isdigit():
        return rf"^https?://[^/]+:{frontend_port}$"
    return None


async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    settings = get_chat_settings()
    cleanup_stale_artifacts(settings.artifact_root, settings.stale_after_seconds)
    yield


async def _chat_error_response(
    _request: Request, error: ChatRequestError
) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": error.detail.model_dump(exclude_none=True)},
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="Nexgent Backend",
        version="0.1.0",
        description="Agent-facing APIs for workflow integrations.",
        lifespan=_lifespan,
    )
    app.add_exception_handler(ChatRequestError, _chat_error_response)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_origin_regex=_cors_origin_regex(),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Preview-Kind"],
    )
    app.add_api_route(
        "/health",
        health_check,
        methods=["GET"],
        include_in_schema=False,
    )
    app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
    app.include_router(rag_chat_router, prefix="/api/rag/chat", tags=["rag-chat"])
    app.include_router(nextcloud_router, prefix="/api/nextcloud", tags=["nextcloud"])
    return app


app = create_app()
