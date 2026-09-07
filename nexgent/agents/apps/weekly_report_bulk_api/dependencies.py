"""Environment-backed composition for the weekly-report bulk control API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ax_persistence import AsyncpgBulkJobStore, LocalBulkArtifactStore

from .service import WeeklyReportBulkControlService


@dataclass(frozen=True, slots=True)
class BulkApiSettings:
    database_dsn: str
    artifact_root: Path
    artifact_min_free_bytes: int
    worker_concurrency: int
    status_poll_seconds: float

    @classmethod
    def from_env(cls) -> BulkApiSettings:
        database_dsn = os.environ.get("WEEKLY_REPORT_JOB_DATABASE_DSN", "")
        if not database_dsn:
            raise ValueError("WEEKLY_REPORT_JOB_DATABASE_DSN must not be empty")
        worker_concurrency = int(
            os.environ.get("WEEKLY_REPORT_WORKER_CONCURRENCY", "32")
        )
        if not 1 <= worker_concurrency <= 512:
            raise ValueError(
                "WEEKLY_REPORT_WORKER_CONCURRENCY must be between 1 and 512"
            )
        status_poll_seconds = float(
            os.environ.get("WEEKLY_REPORT_STATUS_POLL_SECONDS", "2")
        )
        if not 0.5 <= status_poll_seconds <= 30:
            raise ValueError(
                "WEEKLY_REPORT_STATUS_POLL_SECONDS must be between 0.5 and 30"
            )
        return cls(
            database_dsn=database_dsn,
            artifact_root=Path(
                os.environ.get(
                    "WEEKLY_REPORT_ARTIFACT_ROOT", "/var/lib/ax/weekly-reports"
                )
            ),
            artifact_min_free_bytes=int(
                os.environ.get(
                    "WEEKLY_REPORT_ARTIFACT_MIN_FREE_BYTES", str(10 * 1024**3)
                )
            ),
            worker_concurrency=worker_concurrency,
            status_poll_seconds=status_poll_seconds,
        )


def build_default_service() -> tuple[
    AsyncpgBulkJobStore, WeeklyReportBulkControlService
]:
    settings = BulkApiSettings.from_env()
    store = AsyncpgBulkJobStore(settings.database_dsn)
    artifacts = LocalBulkArtifactStore(
        settings.artifact_root,
        minimum_free_bytes=settings.artifact_min_free_bytes,
    )
    return store, WeeklyReportBulkControlService(
        store,
        artifacts,
        worker_concurrency=settings.worker_concurrency,
        status_poll_seconds=settings.status_poll_seconds,
    )
