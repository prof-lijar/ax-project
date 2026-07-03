from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.nextcloud.router import router as nextcloud_router

DEV_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://192.168.0.18:5173",
    "http://192.168.0.18:5174",
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Workflow Helper Backend",
        version="0.1.0",
        description="Agent-facing APIs for workflow integrations.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    app.include_router(nextcloud_router, prefix="/api/nextcloud", tags=["nextcloud"])
    return app


app = create_app()
