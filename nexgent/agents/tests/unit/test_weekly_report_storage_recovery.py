from datetime import date
from uuid import uuid4

import pytest
from ax_contracts import (
    NarrativeGenerationMetadata,
    WeeklyReportBulkJobRequest,
    WeeklyReportRequest,
)
from ax_persistence import ArtifactStoreError, LocalBulkArtifactStore

from apps.workers.recover_weekly_report_storage import read_record, validate_selection
from workflows.weekly_report.agents.reporter.fallback import build_fallback
from workflows.weekly_report.domain.derived_metrics import build_fact_package
from workflows.weekly_report.domain.rendering import render_report
from workflows.weekly_report.tools.source_repository import (
    MockWeeklyReportSourceRepository,
)


@pytest.fixture
def job():
    return {"job_kind": "weekly_report_export_v1", "status": "failed"}


def test_recovery_selects_only_completed_reports(job):
    completed = {"status": "completed", "item_key": "101"}
    assert validate_selection(job, [completed, {"status": "failed"}], 1) == [completed]


@pytest.mark.parametrize("status", ["running", "finalizing", "pending", "expired"])
def test_recovery_rejects_nonrecoverable_jobs(job, status):
    with pytest.raises(ValueError, match="terminal"):
        validate_selection({**job, "status": status}, [], 1)


def test_recovery_rejects_changed_count_and_unfinished_items(job):
    with pytest.raises(ValueError, match="count"):
        validate_selection(job, [{"status": "completed", "item_key": "101"}], 6436)
    with pytest.raises(ValueError, match="unfinished"):
        validate_selection(job, [{"status": "leased"}], 1)
    with pytest.raises(ValueError, match="duplicate"):
        validate_selection(job, [{"status": "completed", "item_key": "101"}] * 2, 2)


@pytest.mark.asyncio
async def test_recovery_verifies_artifacts_and_builds_existing_storage_contract(
    tmp_path,
):
    job_id = uuid4()
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 31), max_reports=1, idempotency_key="recovery-test"
    )
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=request.week_start, ward_ids=[101])
    )
    metrics = source.items[0]
    report = render_report(
        metrics,
        build_fallback(build_fact_package(metrics)),
        "template_fallback",
        NarrativeGenerationMetadata(
            prompt_version="test", validation_status="fallback"
        ),
    )
    artifacts = LocalBulkArtifactStore(tmp_path, minimum_free_bytes=0)
    output = artifacts.write_json(
        job_id, "reports/101.json", report.model_dump(mode="json")
    )
    item = {
        "item_key": "101",
        "output_uri": output.uri,
        "output_checksum": output.sha256,
    }
    record = read_record(artifacts, job_id, request, item)
    assert record.ward_id == 101
    assert record.week_start_date == date(2026, 8, 31)
    assert record.week_end_date == date(2026, 9, 6)
    assert record.report_data_json == report.template_data.model_dump_json()

    with pytest.raises(ValueError, match="belong"):
        read_record(artifacts, uuid4(), request, item)
    with pytest.raises(ValueError, match="week"):
        read_record(
            artifacts,
            job_id,
            request.model_copy(update={"week_start": date(2026, 8, 24)}),
            item,
        )
    artifacts.local_path(output.uri).write_text("{}")
    with pytest.raises(ArtifactStoreError, match="checksum"):
        read_record(artifacts, job_id, request, item)


@pytest.mark.asyncio
@pytest.mark.parametrize("write, skip", [(False, False), (True, False), (True, True)])
async def test_recovery_preflights_and_writes_only_when_requested(
    monkeypatch, capsys, write, skip
):
    import argparse
    import json
    from unittest.mock import AsyncMock, MagicMock

    from apps.workers import recover_weekly_report_storage as recovery
    from workflows.weekly_report.bulk.report_store import (
        WeeklyReportStorageRecord,
        WeeklyReportStorageRejection,
        WeeklyReportStorageResult,
    )

    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 31), max_reports=1, idempotency_key="recovery-test"
    )
    connection = MagicMock()
    connection.fetchrow = AsyncMock(
        return_value={
            "job_kind": "weekly_report_export_v1",
            "status": "failed",
            "request": request.model_dump_json(),
        }
    )
    connection.fetch = AsyncMock(
        return_value=[{"status": "completed", "item_key": "101"}]
    )
    connection.close = AsyncMock()
    monkeypatch.setenv("WEEKLY_REPORT_JOB_DATABASE_DSN", "postgresql://test")
    monkeypatch.setenv("WEEKLY_REPORT_STORAGE_DATABASE_DSN", "postgresql://test")
    monkeypatch.setattr(recovery.asyncpg, "connect", AsyncMock(return_value=connection))
    calls = []

    def read(*args):
        calls.append("read")
        return WeeklyReportStorageRecord(
            101, date(2026, 8, 31), date(2026, 9, 6), None, "자료 없음", "{}"
        )

    monkeypatch.setattr(recovery, "read_record", read)
    writer = MagicMock()
    writer.start = AsyncMock(side_effect=lambda: calls.append("start"))
    writer.close = AsyncMock()

    async def upsert(reports):
        return len([record async for record in reports])

    writer.upsert_reports = AsyncMock(side_effect=upsert)

    async def skip_upsert(reports):
        await upsert(reports)
        return WeeklyReportStorageResult(
            0, (WeeklyReportStorageRejection(101, "weekly_score"),)
        )

    writer.upsert_reports_skipping_not_null = AsyncMock(side_effect=skip_upsert)
    factory = MagicMock(return_value=writer)
    monkeypatch.setattr(recovery, "AsyncpgWeeklyReportStore", factory)
    exit_code = await recovery.recover(
        argparse.Namespace(
            job_id=uuid4(), expected_count=1, write=write, skip_not_null=skip
        )
    )
    result = json.loads(capsys.readouterr().out)
    assert result["verified_count"] == 1
    assert result["written_count"] == int(write and not skip)
    assert result["skipped_count"] == int(skip)
    assert exit_code == (2 if skip else 0)
    assert result["storage_status"] == (
        "failed" if skip else "completed" if write else "validated"
    )
    if skip:
        assert result["skipped"] == [
            {"ward_id": 101, "column": "weekly_score", "sqlstate": "23502"}
        ]
    assert result["job_status"] == "failed"
    assert calls == (["read", "start", "read"] if write else ["read"])
    connection.transaction.assert_called_once_with(
        isolation="repeatable_read", readonly=True
    )
    if write:
        writer.close.assert_awaited_once()
    else:
        factory.assert_not_called()
