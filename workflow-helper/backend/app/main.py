from fastapi import FastAPI

from app.nextcloud.router import router as nextcloud_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Workflow Helper Backend",
        version="0.1.0",
        description="Agent-facing APIs for workflow integrations.",
    )
    app.include_router(nextcloud_router, prefix="/api/nextcloud", tags=["nextcloud"])
    return app


app = create_app()

