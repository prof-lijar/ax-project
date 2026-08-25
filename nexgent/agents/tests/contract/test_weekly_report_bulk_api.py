from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from ax_contracts import WeeklyReportBulkJobRequest
from ax_persistence import InMemoryBulkJobStore, LocalBulkArtifactStore

from apps.weekly_report_bulk_api.app import create_app
from apps.weekly_report_bulk_api.service import WeeklyReportBulkControlService
from workflows.weekly_report.bulk import WEEKLY_REPORT_BULK_JOB_KIND


def build_service(tmp_path):
    return WeeklyReportBulkControlService(
        InMemoryBulkJobStore(),
        LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0),
        worker_concurrency=32,
        status_poll_seconds=2,
    )


@pytest.mark.asyncio
async def test_bulk_api_submits_lists_reads_and_cancels_jobs(tmp_path) -> None:
    app = create_app(service=build_service(tmp_path))
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/health/live")).status_code == 200
        assert (await client.get("/health/ready")).status_code == 200
        runtime = (
            await client.get("/v1/weekly-report/bulk/runtime")
        ).json()
        assert runtime["worker_concurrency"] == 32
        assert runtime["source_page_size"] == 100

        created = await client.post(
            "/v1/weekly-report/bulk/jobs",
            json={
                "week_start": "2026-08-03",
                "max_reports": 10_000,
                "idempotency_key": "ui-weekly-2026-08-03",
            },
        )
        assert created.status_code == 201
        job = created.json()
        assert job["status"] == "pending"
        assert job["max_reports"] == 10_000

        listed = (await client.get("/v1/weekly-report/bulk/jobs")).json()
        assert [item["job_id"] for item in listed["jobs"]] == [job["job_id"]]
        fetched = await client.get(
            f"/v1/weekly-report/bulk/jobs/{job['job_id']}"
        )
        assert fetched.json()["job_id"] == job["job_id"]

        cancelled = await client.post(
            f"/v1/weekly-report/bulk/jobs/{job['job_id']}/cancel"
        )
        assert cancelled.json()["status"] == "cancelling"


@pytest.mark.asyncio
async def test_bulk_api_validates_limits_and_missing_jobs(tmp_path) -> None:
    app = create_app(service=build_service(tmp_path))
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        invalid = await client.post(
            "/v1/weekly-report/bulk/jobs",
            json={
                "week_start": "2026-08-04",
                "max_reports": 10_001,
                "idempotency_key": "invalid-weekly-job",
            },
        )
        assert invalid.status_code == 422
        missing = await client.get(
            "/v1/weekly-report/bulk/jobs/00000000-0000-0000-0000-000000000001"
        )
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_bulk_api_downloads_only_verified_terminal_export(tmp_path) -> None:
    service = build_service(tmp_path)
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3),
        max_reports=3,
        idempotency_key="download-weekly-job",
    )
    job = await service.store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND,
        request.idempotency_key,
        request.model_dump(mode="json"),
    )
    artifact = service.artifacts.write_bytes(
        job.job_id, "weekly-reports.zip", b"PK\x05\x06" + b"\x00" * 18
    )
    await service.store.finish_job(
        job.job_id,
        status="completed",
        export_uri=artifact.uri,
        export_checksum=artifact.sha256,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    app = create_app(service=service)

    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/v1/weekly-report/bulk/jobs/{job.job_id}/export"
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.content.startswith(b"PK")
