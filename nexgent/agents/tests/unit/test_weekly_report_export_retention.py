from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from ax_persistence import (
    ArtifactStoreError,
    InMemoryBulkJobStore,
    LocalBulkArtifactStore,
)

from apps.workers.weekly_report import build_parser
from workflows.weekly_report.bulk import (
    WEEKLY_REPORT_BULK_JOB_KIND,
    bulk_job_status,
    cleanup_weekly_report_exports,
)


async def make_export(store, artifacts, index, *, kind=WEEKLY_REPORT_BULK_JOB_KIND):
    job = await store.create_job(kind, f"retention-{index}", {
        "week_start": "2026-08-31", "timezone": "Asia/Seoul", "max_reports": 1,
        "idempotency_key": f"retention-{index}",
    })
    artifact = artifacts.write_bytes(job.job_id, "weekly-reports.zip", b"zip")
    artifacts.write_text(job.job_id, "outputs/1.json", "preserve report")
    await store.finish_job(
        job.job_id, status="completed", export_uri=artifact.uri,
        export_checksum=artifact.sha256, expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    # Completion order differs from submission order and has deterministic ties.
    store.jobs[job.job_id] = replace(
        store.jobs[job.job_id], updated_at=datetime(2026, 9, 9, tzinfo=UTC) + timedelta(seconds=index),
    )
    return job.job_id


@pytest.mark.asyncio
async def test_retains_five_latest_exports_and_preserves_reports_and_active_jobs(tmp_path):
    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    jobs = [await make_export(store, artifacts, i) for i in [7, 1, 6, 0, 5, 2, 4, 3]]
    other = await make_export(store, artifacts, -1, kind="another-workflow")
    active = await make_export(store, artifacts, -2)
    await store.set_job_status(active, "finalizing")
    orphan = await make_export(store, artifacts, -3)
    store.jobs[orphan] = replace(store.jobs[orphan], status="failed", export_uri=None)
    original = {job_id: store.jobs[job_id] for job_id in jobs}

    assert await cleanup_weekly_report_exports(store, artifacts) == 4
    retained = {jobs[i] for i in [0, 2, 4, 6, 7]}
    for job_id in jobs:
        job = await store.get_job(job_id)
        assert (tmp_path / str(job_id) / "weekly-reports.zip").exists() == (job_id in retained)
        assert (tmp_path / str(job_id) / "outputs/1.json").read_text() == "preserve report"
        assert job.status == "completed"
        assert job.updated_at == original[job_id].updated_at
        assert ((await bulk_job_status(store, job_id)).export is not None) == (job_id in retained)
    for job_id in [other, active]:
        assert (tmp_path / str(job_id) / "weekly-reports.zip").exists()
    assert await cleanup_weekly_report_exports(store, artifacts) == 0
    await make_export(store, artifacts, 8)
    assert await cleanup_weekly_report_exports(store, artifacts) == 1
    assert (await store.get_job(jobs[7])).export_uri is None


@pytest.mark.asyncio
async def test_failed_deletion_is_retryable_and_missing_zip_clears_link(tmp_path, monkeypatch):
    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    jobs = [await make_export(store, artifacts, i) for i in range(6)]
    remove = artifacts.remove_file

    def fail(*args):
        raise ArtifactStoreError("cannot remove")

    monkeypatch.setattr(artifacts, "remove_file", fail)
    with pytest.raises(ArtifactStoreError):
        await cleanup_weekly_report_exports(store, artifacts)
    assert (await store.get_job(jobs[0])).export_uri is not None
    monkeypatch.setattr(artifacts, "remove_file", remove)
    (tmp_path / str(jobs[0]) / "weekly-reports.zip").unlink()
    assert await cleanup_weekly_report_exports(store, artifacts) == 0
    assert (await store.get_job(jobs[0])).export_uri is None


def test_cleanup_exports_cli():
    assert build_parser().parse_args(["cleanup-exports"]).command == "cleanup-exports"
