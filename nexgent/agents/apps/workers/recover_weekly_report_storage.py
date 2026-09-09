"""Store an existing terminal job's verified reports without rerunning models.

May be streamed into the deployed worker with ``uv run python - JOB_ID ...``.
Uses the existing queue, artifact and report-storage contracts only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
from ax_contracts import WardWeeklyReport, WeeklyReportBulkJobRequest
from ax_persistence import LocalBulkArtifactStore

from workflows.weekly_report.bulk.report_store import (
    AsyncpgWeeklyReportStore,
    WeeklyReportStorageRecord,
    WeeklyReportStorageSettings,
)


def validate_selection(
    job: Mapping[str, Any], items: Sequence[Mapping[str, Any]], expected_count: int
) -> list[Mapping[str, Any]]:
    if job["job_kind"] != "weekly_report_export_v1":
        raise ValueError("job is not a weekly-report export")
    if job["status"] not in {"failed", "partial", "cancelled", "completed"}:
        raise ValueError("recovery requires a terminal, unexpired job")
    if any(
        item["status"] not in {"completed", "failed", "cancelled"} for item in items
    ):
        raise ValueError("job still has unfinished items")
    completed = [item for item in items if item["status"] == "completed"]
    if not 1 <= expected_count <= 10_000 or len(completed) != expected_count:
        raise ValueError("completed report count does not match --expected-count")
    if len({item["item_key"] for item in completed}) != len(completed):
        raise ValueError("duplicate completed item identity")
    return completed


def read_record(
    artifacts: LocalBulkArtifactStore,
    job_id: UUID,
    request: WeeklyReportBulkJobRequest,
    item: Mapping[str, Any],
) -> WeeklyReportStorageRecord:
    if not item["output_uri"] or not item["output_checksum"]:
        raise ValueError("completed item has no verified output")
    ward_id = int(item["item_key"])
    path = artifacts.local_path(item["output_uri"])
    expected = artifacts.root / str(job_id) / "reports" / f"{ward_id}.json"
    if path != expected.resolve():
        raise ValueError("output artifact does not belong to this job and ward")
    report = WardWeeklyReport.model_validate(
        artifacts.read_verified_json(item["output_uri"], item["output_checksum"])
    )
    if (
        report.ward_id != ward_id
        or report.metrics.ward_id != ward_id
        or report.metrics.week_start != request.week_start
    ):
        raise ValueError("report identity or reporting week does not match the job")
    return WeeklyReportStorageRecord.from_report(report)


async def records(
    artifacts: LocalBulkArtifactStore,
    job_id: UUID,
    request: WeeklyReportBulkJobRequest,
    items: Sequence[Mapping[str, Any]],
) -> AsyncIterator[WeeklyReportStorageRecord]:
    for item in items:
        yield await asyncio.to_thread(read_record, artifacts, job_id, request, item)


async def recover(args: argparse.Namespace) -> int:
    connection = await asyncpg.connect(
        os.environ["WEEKLY_REPORT_JOB_DATABASE_DSN"],
        timeout=10,
        command_timeout=120,
    )
    try:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            job = await connection.fetchrow(
                "SELECT job_kind, status, request FROM ax_bulk_jobs WHERE job_id = $1",
                args.job_id,
            )
            if job is None:
                raise ValueError("job does not exist")
            items = await connection.fetch(
                "SELECT item_key, status, output_uri, output_checksum "
                "FROM ax_bulk_items WHERE job_id = $1 ORDER BY item_key",
                args.job_id,
            )
    finally:
        await connection.close()

    completed = validate_selection(job, items, args.expected_count)
    request = WeeklyReportBulkJobRequest.model_validate(json.loads(job["request"]))
    artifacts = LocalBulkArtifactStore(
        Path(
            os.environ.get("WEEKLY_REPORT_ARTIFACT_ROOT", "/var/lib/ax/weekly-reports")
        )
    )
    # Verify all files before opening the target writer; reread inside its single
    # transaction so a later artifact failure also rolls back earlier batches.
    async for _ in records(artifacts, args.job_id, request, completed):
        pass
    result = {
        "job_id": str(args.job_id),
        "job_status": job["status"],
        "verified_count": len(completed),
        "week_start": request.week_start.isoformat(),
        "target": "ansimk.resources_ward_weekly_report",
        "written_count": 0,
        "skipped_count": 0,
        "skipped": [],
        "storage_status": "validated",
    }
    if args.write:
        writer = AsyncpgWeeklyReportStore(WeeklyReportStorageSettings.from_env())
        try:
            await writer.start()
            if args.skip_not_null:
                outcome = await writer.upsert_reports_skipping_not_null(
                    records(artifacts, args.job_id, request, completed)
                )
                result["written_count"] = outcome.written_count
                result["skipped_count"] = len(outcome.skipped)
                result["skipped"] = [asdict(item) for item in outcome.skipped]
            else:
                result["written_count"] = await writer.upsert_reports(
                    records(artifacts, args.job_id, request, completed)
                )
            result["storage_status"] = (
                "completed"
                if not result["skipped_count"]
                else "partial"
                if result["written_count"]
                else "failed"
            )
        finally:
            await writer.close()
    print(json.dumps(result))
    return 2 if result["skipped_count"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id", type=UUID)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--write", action="store_true", help="upsert verified reports")
    parser.add_argument(
        "--skip-not-null",
        action="store_true",
        help="skip reports rejected by NOT NULL constraints; requires --write",
    )
    args = parser.parse_args()
    if args.skip_not_null and not args.write:
        parser.error("--skip-not-null requires --write")
    try:
        return asyncio.run(recover(args))
    except Exception as exc:  # noqa: BLE001 - do not print DSNs or report content
        cause = exc
        while cause.__cause__ is not None:
            cause = cause.__cause__
        print(
            json.dumps(
                {
                    "error": type(exc).__name__,
                    "cause": type(cause).__name__,
                    "sqlstate": getattr(cause, "sqlstate", None),
                    "column": getattr(cause, "column_name", None),
                    "message": "Recovery did not finish successfully; inspect the error code before retrying.",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
