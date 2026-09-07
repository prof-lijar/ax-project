"""Private operator API for durable high-volume weekly-report jobs."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

from ax_contracts import (
    WeeklyReportBulkJobList,
    WeeklyReportBulkJobRequest,
    WeeklyReportBulkJobStatus,
    WeeklyReportBulkRuntime,
)
from ax_persistence import (
    ArtifactStoreError,
    AsyncpgBulkJobStore,
    BulkStoreError,
)
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from .dependencies import build_default_service
from .service import WeeklyReportBulkControlService


def create_app(*, service: WeeklyReportBulkControlService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned_store: AsyncpgBulkJobStore | None = None
        try:
            resolved_service = service
            if resolved_service is None:
                owned_store, resolved_service = build_default_service()
                await owned_store.start()
            await resolved_service.ready()
            app.state.bulk_service = resolved_service
        except (ArtifactStoreError, BulkStoreError, OSError, ValueError):
            app.state.bulk_service = None
        yield
        if owned_store is not None:
            await owned_store.close()

    app = FastAPI(
        title="AX Weekly Report Bulk API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.bulk_service = service

    def required_service() -> WeeklyReportBulkControlService:
        resolved = getattr(app.state, "bulk_service", None)
        if resolved is None:
            raise HTTPException(status_code=503, detail="bulk service is not ready")
        return resolved

    @app.get("/health/live")
    async def live() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/health/ready")
    async def ready() -> dict[str, bool]:
        resolved = required_service()
        try:
            await resolved.ready()
        except (ArtifactStoreError, BulkStoreError, OSError):
            raise HTTPException(status_code=503, detail="bulk service is not ready") from None
        return {"ok": True}

    @app.get(
        "/v1/weekly-report/bulk/runtime",
        response_model=WeeklyReportBulkRuntime,
    )
    async def runtime() -> WeeklyReportBulkRuntime:
        return required_service().runtime

    @app.post(
        "/v1/weekly-report/bulk/jobs",
        response_model=WeeklyReportBulkJobStatus,
        status_code=201,
    )
    async def submit(
        payload: WeeklyReportBulkJobRequest,
    ) -> WeeklyReportBulkJobStatus:
        try:
            return await required_service().submit(payload)
        except BulkStoreError as exc:
            raise _store_error(exc) from exc

    @app.get(
        "/v1/weekly-report/bulk/jobs",
        response_model=WeeklyReportBulkJobList,
    )
    async def list_jobs(
        limit: int = Query(default=20, ge=1, le=100),
    ) -> WeeklyReportBulkJobList:
        try:
            return await required_service().list(limit)
        except BulkStoreError as exc:
            raise _store_error(exc) from exc

    @app.get(
        "/v1/weekly-report/bulk/jobs/{job_id}",
        response_model=WeeklyReportBulkJobStatus,
    )
    async def status(job_id: UUID) -> WeeklyReportBulkJobStatus:
        try:
            return await required_service().status(job_id)
        except BulkStoreError as exc:
            raise _store_error(exc) from exc

    @app.post(
        "/v1/weekly-report/bulk/jobs/{job_id}/cancel",
        response_model=WeeklyReportBulkJobStatus,
    )
    async def cancel(job_id: UUID) -> WeeklyReportBulkJobStatus:
        try:
            return await required_service().cancel(job_id)
        except BulkStoreError as exc:
            raise _store_error(exc) from exc

    @app.get("/v1/weekly-report/bulk/jobs/{job_id}/export")
    async def download(job_id: UUID) -> Response:
        try:
            path = await required_service().export_path(job_id)
        except (ArtifactStoreError, BulkStoreError) as exc:
            raise _store_error(exc) from exc
        return AsyncChunkedFileResponse(
            path,
            media_type="application/zip",
            filename=f"weekly-reports-{job_id}.zip",
        )

    return app


def _store_error(error: Exception) -> HTTPException:
    message = str(error)
    status_code = 404 if "not found" in message or "not available" in message else 409
    return HTTPException(status_code=status_code, detail=message)


app = create_app()


class AsyncChunkedFileResponse(Response):
    """Send a verified local export in bounded chunks without full buffering."""

    def __init__(self, path: Path, *, media_type: str, filename: str) -> None:
        content_length = path.stat().st_size
        super().__init__(
            content=b"",
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(content_length),
            },
        )
        self.path = path

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        del scope, receive
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self.raw_headers,
            }
        )
        with self.path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": True,
                    }
                )
        await send(
            {"type": "http.response.body", "body": b"", "more_body": False}
        )
