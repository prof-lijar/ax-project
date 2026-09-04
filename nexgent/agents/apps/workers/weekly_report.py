"""Operator CLI for durable high-volume weekly-report exports."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

from ax_contracts import WeeklyReportBulkJobRequest
from ax_evals import evaluate_weekly_report_bulk_capacity
from ax_integrations import get_default_chat_model
from ax_persistence import (
    AsyncpgBulkJobStore,
    BulkJobStore,
    LocalBulkArtifactStore,
    utc_now,
)

from workflows.weekly_report.bulk import (
    WEEKLY_REPORT_BULK_JOB_KIND,
    AsyncpgWeeklyReportStore,
    WeeklyReportBulkRunner,
    WeeklyReportStorageSettings,
    bulk_job_status,
)
from workflows.weekly_report.tools import get_weekly_report_source_repository


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    database_dsn: str
    artifact_root: Path
    artifact_min_free_bytes: int
    concurrency: int
    active_job_limit: int
    poll_seconds: float
    item_timeout_seconds: float

    @classmethod
    def from_env(cls) -> WorkerSettings:
        dsn = os.environ.get("WEEKLY_REPORT_JOB_DATABASE_DSN", "")
        if not dsn:
            raise ValueError("WEEKLY_REPORT_JOB_DATABASE_DSN must not be empty")
        root = Path(
            os.environ.get("WEEKLY_REPORT_ARTIFACT_ROOT", "/var/lib/ax/weekly-reports")
        )
        concurrency = int(os.environ.get("WEEKLY_REPORT_WORKER_CONCURRENCY", "32"))
        if not 1 <= concurrency <= 512:
            raise ValueError(
                "WEEKLY_REPORT_WORKER_CONCURRENCY must be between 1 and 512"
            )
        active_job_limit = int(
            os.environ.get("WEEKLY_REPORT_ACTIVE_JOB_LIMIT", "4")
        )
        if not 1 <= active_job_limit <= 32:
            raise ValueError(
                "WEEKLY_REPORT_ACTIVE_JOB_LIMIT must be between 1 and 32"
            )
        item_timeout_seconds = float(
            os.environ.get("WEEKLY_REPORT_ITEM_TIMEOUT_SECONDS", "60")
        )
        if not 1 <= item_timeout_seconds <= 600:
            raise ValueError(
                "WEEKLY_REPORT_ITEM_TIMEOUT_SECONDS must be between 1 and 600"
            )
        return cls(
            database_dsn=dsn,
            artifact_root=root,
            artifact_min_free_bytes=int(
                os.environ.get(
                    "WEEKLY_REPORT_ARTIFACT_MIN_FREE_BYTES", str(10 * 1024**3)
                )
            ),
            concurrency=concurrency,
            active_job_limit=active_job_limit,
            poll_seconds=float(
                os.environ.get("WEEKLY_REPORT_WORKER_POLL_SECONDS", "1")
            ),
            item_timeout_seconds=item_timeout_seconds,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weekly-report-worker")
    commands = parser.add_subparsers(dest="command", required=True)
    submit = commands.add_parser("submit", help="create or return an idempotent job")
    submit.add_argument("--week-start", required=True, type=date.fromisoformat)
    submit.add_argument("--idempotency-key", required=True)
    submit.add_argument("--timezone", default="Asia/Seoul")
    submit.add_argument("--max-reports", type=int, default=10_000)
    submit.add_argument("--cursor")
    run = commands.add_parser("run", help="run one job until terminal")
    run.add_argument("job_id", type=UUID)
    run.add_argument("--concurrency", type=int)
    commands.add_parser("serve", help="continuously run bounded concurrent jobs")
    status = commands.add_parser("status", help="show content-free progress")
    status.add_argument("job_id", type=UUID)
    cancel = commands.add_parser("cancel", help="request cooperative cancellation")
    cancel.add_argument("job_id", type=UUID)
    export = commands.add_parser("export", help="copy a completed private ZIP")
    export.add_argument("job_id", type=UUID)
    export.add_argument("destination", type=Path)
    commands.add_parser("cleanup", help="expire artifacts past their retention time")
    capacity = commands.add_parser("capacity", help="evaluate an observed load run")
    capacity.add_argument("--reports", type=int, required=True)
    capacity.add_argument("--elapsed-seconds", type=float, required=True)
    return parser


async def run_command(args: argparse.Namespace, settings: WorkerSettings) -> int:
    store = AsyncpgBulkJobStore(settings.database_dsn)
    report_store: AsyncpgWeeklyReportStore | None = None
    artifacts = LocalBulkArtifactStore(
        settings.artifact_root, minimum_free_bytes=settings.artifact_min_free_bytes
    )
    await store.start()
    try:
        if args.command == "submit":
            request = WeeklyReportBulkJobRequest(
                week_start=args.week_start,
                timezone=args.timezone,
                max_reports=args.max_reports,
                cursor=args.cursor,
                idempotency_key=args.idempotency_key,
            )
            job = await store.create_job(
                WEEKLY_REPORT_BULK_JOB_KIND,
                request.idempotency_key,
                request.model_dump(mode="json"),
            )
            _print_json(await bulk_job_status(store, job.job_id))
            return 0
        if args.command == "status":
            _print_json(await bulk_job_status(store, args.job_id))
            return 0
        if args.command == "cancel":
            await store.request_cancel(args.job_id)
            _print_json(await bulk_job_status(store, args.job_id))
            return 0
        if args.command == "export":
            status = await bulk_job_status(store, args.job_id)
            if status.export is None:
                raise RuntimeError("bulk job has no completed export")
            source = artifacts.local_path(status.export.uri)
            destination = args.destination.expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            destination.chmod(0o600)
            print(destination)
            return 0
        if args.command == "cleanup":
            expired = await store.expire_jobs(utc_now())
            for job_id in expired:
                artifacts.remove_job(job_id)
            print(json.dumps({"expired_count": len(expired)}))
            return 0

        model = get_default_chat_model()
        report_store = AsyncpgWeeklyReportStore(
            WeeklyReportStorageSettings.from_env()
        )
        await report_store.start()
        runner = WeeklyReportBulkRunner(
            store,
            artifacts,
            get_weekly_report_source_repository(),
            model,
            report_store,
            poll_seconds=settings.poll_seconds,
            item_timeout_seconds=settings.item_timeout_seconds,
            item_semaphore=asyncio.Semaphore(settings.concurrency),
        )
        if args.command == "run":
            status = await runner.run(
                args.job_id, concurrency=args.concurrency or settings.concurrency
            )
            _print_json(status)
            return 0
        await _serve_jobs(
            store,
            runner,
            active_job_limit=settings.active_job_limit,
            item_concurrency=settings.concurrency,
            poll_seconds=settings.poll_seconds,
        )
        return 0
    finally:
        if report_store is not None:
            await report_store.close()
        await store.close()


async def _serve_jobs(
    store: BulkJobStore,
    runner: Any,
    *,
    active_job_limit: int,
    item_concurrency: int,
    poll_seconds: float,
) -> None:
    """Admit distinct jobs concurrently and recover each task independently."""

    if not 1 <= active_job_limit <= 32:
        raise ValueError("active_job_limit must be between 1 and 32")
    active: dict[UUID, asyncio.Task[Any]] = {}
    retry_not_before: dict[UUID, float] = {}
    logger = logging.getLogger(__name__)
    loop = asyncio.get_running_loop()
    try:
        while True:
            now = loop.time()
            retry_not_before = {
                job_id: retry_at
                for job_id, retry_at in retry_not_before.items()
                if retry_at > now
            }
            for job_id, task in list(active.items()):
                if not task.done():
                    continue
                del active[job_id]
                try:
                    await task
                except Exception:
                    retry_not_before[job_id] = loop.time() + poll_seconds
                    logger.exception(
                        "weekly report bulk job loop recovered",
                        extra={"job_id": str(job_id)},
                    )

            while len(active) < active_job_limit:
                job = await store.next_job(
                    WEEKLY_REPORT_BULK_JOB_KIND,
                    exclude_job_ids=active.keys() | retry_not_before.keys(),
                )
                if job is None:
                    break
                logger.info(
                    "weekly report bulk job admitted",
                    extra={
                        "job_id": str(job.job_id),
                        "active_jobs": len(active) + 1,
                        "active_job_limit": active_job_limit,
                        "item_concurrency": item_concurrency,
                    },
                )
                active[job.job_id] = asyncio.create_task(
                    runner.run(job.job_id, concurrency=item_concurrency),
                    name=f"weekly-report-job-{job.job_id}",
                )

            if not active:
                await asyncio.sleep(poll_seconds)
                continue
            await asyncio.wait(
                active.values(),
                timeout=poll_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
    finally:
        for task in active.values():
            task.cancel()
        await asyncio.gather(*active.values(), return_exceptions=True)


def _print_json(value: object) -> None:
    if hasattr(value, "model_dump_json"):
        print(value.model_dump_json(indent=2))
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args()
    if args.command == "capacity":
        if args.reports < 1 or args.elapsed_seconds <= 0:
            raise SystemExit("reports and elapsed-seconds must be positive")
        observed = args.reports / args.elapsed_seconds
        _print_json(
            {
                "observed_reports_per_second": observed,
                "evaluations": [
                    result.model_dump(mode="json")
                    for result in evaluate_weekly_report_bulk_capacity(observed)
                ],
            }
        )
        raise SystemExit(0)
    raise SystemExit(asyncio.run(run_command(args, WorkerSettings.from_env())))


if __name__ == "__main__":
    main()
