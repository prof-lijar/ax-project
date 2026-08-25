"""Application service for safe bulk-job control and export access."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from ax_contracts import (
    WeeklyReportBulkJobList,
    WeeklyReportBulkJobRequest,
    WeeklyReportBulkJobStatus,
    WeeklyReportBulkRuntime,
)
from ax_persistence import BulkJobStore, BulkStoreError, LocalBulkArtifactStore

from workflows.weekly_report.bulk import (
    WEEKLY_REPORT_BULK_JOB_KIND,
    bulk_job_status,
)


class WeeklyReportBulkControlService:
    """Content-free job control backed by the durable bulk store."""

    def __init__(
        self,
        store: BulkJobStore,
        artifacts: LocalBulkArtifactStore,
        *,
        worker_concurrency: int,
        status_poll_seconds: float = 2.0,
    ) -> None:
        self.store = store
        self.artifacts = artifacts
        self.runtime = WeeklyReportBulkRuntime(
            worker_concurrency=worker_concurrency,
            status_poll_seconds=status_poll_seconds,
        )

    async def ready(self) -> bool:
        await self.store.list_jobs(WEEKLY_REPORT_BULK_JOB_KIND, limit=1)
        self.artifacts.prepare()
        return True

    async def submit(
        self, request: WeeklyReportBulkJobRequest
    ) -> WeeklyReportBulkJobStatus:
        job = await self.store.create_job(
            WEEKLY_REPORT_BULK_JOB_KIND,
            request.idempotency_key,
            request.model_dump(mode="json"),
        )
        return await bulk_job_status(self.store, job.job_id)

    async def list(self, limit: int) -> WeeklyReportBulkJobList:
        jobs = await self.store.list_jobs(WEEKLY_REPORT_BULK_JOB_KIND, limit)
        return WeeklyReportBulkJobList(
            jobs=[await bulk_job_status(self.store, job.job_id) for job in jobs]
        )

    async def status(self, job_id: UUID) -> WeeklyReportBulkJobStatus:
        return await bulk_job_status(self.store, job_id)

    async def cancel(self, job_id: UUID) -> WeeklyReportBulkJobStatus:
        await self.store.get_job(job_id)
        await self.store.request_cancel(job_id)
        return await bulk_job_status(self.store, job_id)

    async def export_path(self, job_id: UUID) -> Path:
        status = await bulk_job_status(self.store, job_id)
        if status.export is None or status.export.checksum is None:
            raise BulkStoreError("bulk job export is not available")
        path = self.artifacts.local_path(status.export.uri)
        if self.artifacts.describe(path).sha256 != status.export.checksum:
            raise BulkStoreError("bulk job export checksum does not match")
        return path
