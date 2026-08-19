"""Private FastAPI boundary for deterministic weekly-report source metadata."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Protocol

from ax_contracts import WeeklyReportRequest, WeeklyReportSourceResponse
from ax_integrations import DatabaseUnavailable, ReadOnlyDatabase
from fastapi import FastAPI, HTTPException

from workflows.weekly_report.source.service import SourceRequestError

from .dependencies import build_default_service


class SourceService(Protocol):
    async def health(self) -> bool: ...

    async def build(self, request: WeeklyReportRequest) -> WeeklyReportSourceResponse: ...


def create_app(
    *,
    service: SourceService | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned_database: ReadOnlyDatabase | None = None
        try:
            resolved_service = service
            if resolved_service is None:
                owned_database, resolved_service = build_default_service()
                await owned_database.start()
            app.state.source_service = resolved_service
            app.state.startup_error = None
        except (ValueError, DatabaseUnavailable) as exc:
            app.state.source_service = None
            app.state.startup_error = str(exc)
        yield
        if owned_database is not None:
            await owned_database.close()

    app = FastAPI(
        title="AX Weekly Report Source API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.source_service = service
    app.state.startup_error = None

    @app.get("/health/live")
    async def live() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/health/ready")
    async def ready() -> dict[str, bool]:
        source_service = getattr(app.state, "source_service", None)
        if source_service is None or not await source_service.health():
            raise HTTPException(status_code=503, detail="source service is not ready")
        return {"ok": True}

    @app.post(
        "/internal/v1/weekly-report/source",
        response_model=WeeklyReportSourceResponse,
    )
    async def build_source(
        payload: WeeklyReportRequest,
    ) -> WeeklyReportSourceResponse:
        source_service = getattr(app.state, "source_service", None)
        if source_service is None:
            raise HTTPException(status_code=503, detail="source service is not configured")
        try:
            return await source_service.build(payload)
        except SourceRequestError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except DatabaseUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return app


app = create_app()
