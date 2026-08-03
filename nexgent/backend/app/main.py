import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.nextcloud.router import router as nextcloud_router

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


def create_app() -> FastAPI:
    app = FastAPI(
        title="Nexgent Backend",
        version="0.1.0",
        description="Agent-facing APIs for workflow integrations.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_origin_regex=_cors_origin_regex(),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Preview-Kind"],
    )
    app.add_api_route(
        "/health",
        health_check,
        methods=["GET"],
        include_in_schema=False,
    )
    app.include_router(nextcloud_router, prefix="/api/nextcloud", tags=["nextcloud"])
    return app


app = create_app()
