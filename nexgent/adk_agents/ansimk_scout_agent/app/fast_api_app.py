from __future__ import annotations

import logging
import os

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import ScoutSettings
from app.models import ScoutRunErrorResponse, ScoutRunRequest, ScoutRunResponse
from app.services.run_service import (
    ScoutRunFailedError,
    ScoutRunService,
    build_default_run_service,
)

LOGGER = logging.getLogger(__name__)
FRONTEND_ORIGIN = "http://192.168.0.18:5173"


def create_app(run_service: ScoutRunService | None = None) -> FastAPI:
    service = run_service or build_default_run_service(ScoutSettings.from_env())
    api = FastAPI(
        title="ansimk Scout Agent API",
        version="0.1.0",
        description="Standalone bounded Google ADK web-research POC.",
    )
    api.add_middleware(
        CORSMiddleware,
        allow_origins=[FRONTEND_ORIGIN],
        allow_credentials=False,
        allow_methods=["POST"],
        allow_headers=["Accept", "Content-Type"],
    )

    @api.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/health/ready")
    async def ready() -> dict[str, str]:
        if not service.is_ready():
            raise HTTPException(status_code=503, detail="Scout service is not configured.")
        return {"status": "ready"}

    @api.post(
        "/v1/scout/runs",
        response_model=ScoutRunResponse,
        responses={502: {"model": ScoutRunErrorResponse}},
    )
    async def create_run(request: ScoutRunRequest) -> ScoutRunResponse | JSONResponse:
        if not service.is_ready():
            raise HTTPException(status_code=503, detail="Scout service is not configured.")
        try:
            return await service.run(request)
        except ScoutRunFailedError as exc:
            LOGGER.warning("Scout run failed", extra={"run_id": exc.run.run_id})
            error_response = ScoutRunErrorResponse(
                detail="Scout run failed.",
                run=exc.run,
            )
            return JSONResponse(
                status_code=502,
                content=jsonable_encoder(error_response),
            )
        except Exception as exc:
            LOGGER.warning("Scout run failed", extra={"error_type": type(exc).__name__})
            raise HTTPException(status_code=502, detail="Scout run failed.") from None

    return api


app = create_app()


def main() -> None:
    logging.basicConfig(level=os.getenv("SCOUT_LOG_LEVEL", "INFO"))
    uvicorn.run(
        "app.fast_api_app:app",
        host=os.getenv("SCOUT_HOST", "127.0.0.1"),
        port=int(os.getenv("SCOUT_PORT", "8091")),
        reload=False,
    )


if __name__ == "__main__":
    main()
