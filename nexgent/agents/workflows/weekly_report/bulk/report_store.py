"""Durable storage for generated frontend weekly-report JSON."""

from __future__ import annotations

import os
from collections.abc import AsyncIterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

import asyncpg
from ax_contracts import WardWeeklyReport

_UPSERT_REPORT_SQL = """
INSERT INTO ansimk.resources_ward_weekly_report (
    ward_id,
    week_start_date,
    week_end_date,
    weekly_score,
    weekly_status,
    report_data,
    created_at,
    updated_at
)
VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW(), NOW())
ON CONFLICT (ward_id, week_start_date) DO UPDATE SET
    week_end_date = EXCLUDED.week_end_date,
    weekly_score = EXCLUDED.weekly_score,
    weekly_status = EXCLUDED.weekly_status,
    report_data = EXCLUDED.report_data,
    updated_at = NOW()
"""


class WeeklyReportStorageConfigurationError(ValueError):
    """Safe invalid writer configuration error."""


class WeeklyReportStorageUnavailable(RuntimeError):
    """Safe report-storage failure without credentials or report content."""


@dataclass(frozen=True, slots=True)
class WeeklyReportStorageSettings:
    dsn: str = field(repr=False)
    min_pool_size: int = 1
    max_pool_size: int = 2
    batch_size: int = 500
    connect_timeout_seconds: float = 10.0
    command_timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if not self.dsn:
            raise WeeklyReportStorageConfigurationError(
                "WEEKLY_REPORT_STORAGE_DATABASE_DSN must not be empty"
            )
        if self.min_pool_size < 1 or self.max_pool_size < self.min_pool_size:
            raise WeeklyReportStorageConfigurationError(
                "weekly-report storage pool sizes are invalid"
            )
        if self.max_pool_size > 10:
            raise WeeklyReportStorageConfigurationError(
                "weekly-report storage maximum pool size is too large"
            )
        if not 1 <= self.batch_size <= 1_000:
            raise WeeklyReportStorageConfigurationError(
                "weekly-report storage batch size must be between 1 and 1000"
            )
        if self.connect_timeout_seconds <= 0 or self.command_timeout_seconds <= 0:
            raise WeeklyReportStorageConfigurationError(
                "weekly-report storage timeouts must be positive"
            )

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> WeeklyReportStorageSettings:
        values = os.environ if environ is None else environ
        try:
            return cls(
                dsn=(
                    values.get("WEEKLY_REPORT_STORAGE_DATABASE_DSN", "")
                    or values.get("ANSIMK_DATABASE_DSN", "")
                ),
                min_pool_size=int(
                    values.get("WEEKLY_REPORT_STORAGE_MIN_POOL_SIZE", "1")
                ),
                max_pool_size=int(
                    values.get("WEEKLY_REPORT_STORAGE_MAX_POOL_SIZE", "2")
                ),
                batch_size=int(values.get("WEEKLY_REPORT_STORAGE_BATCH_SIZE", "500")),
                connect_timeout_seconds=float(
                    values.get("WEEKLY_REPORT_STORAGE_CONNECT_TIMEOUT_SECONDS", "10")
                ),
                command_timeout_seconds=float(
                    values.get("WEEKLY_REPORT_STORAGE_COMMAND_TIMEOUT_SECONDS", "120")
                ),
            )
        except WeeklyReportStorageConfigurationError:
            raise
        except ValueError as exc:
            raise WeeklyReportStorageConfigurationError(
                "weekly-report storage numeric configuration is invalid"
            ) from exc


@dataclass(frozen=True, slots=True)
class WeeklyReportStorageRecord:
    ward_id: int
    week_start_date: date
    week_end_date: date
    weekly_score: int | None
    weekly_status: str
    report_data_json: str = field(repr=False)

    @classmethod
    def from_report(cls, report: WardWeeklyReport) -> WeeklyReportStorageRecord:
        basic_info = report.template_data.basic_info
        period = basic_info.period
        expected_end = report.metrics.week_end - timedelta(days=1)
        if (
            period.start_date != report.metrics.week_start
            or period.end_date != expected_end
        ):
            raise ValueError("weekly-report storage period does not match metrics")
        return cls(
            ward_id=report.ward_id,
            week_start_date=period.start_date,
            week_end_date=period.end_date,
            weekly_score=basic_info.risk_score,
            weekly_status=basic_info.status,
            report_data_json=report.template_data.model_dump_json(),
        )

    def sql_parameters(self) -> tuple[object, ...]:
        return (
            self.ward_id,
            self.week_start_date,
            self.week_end_date,
            self.weekly_score,
            self.weekly_status,
            self.report_data_json,
        )


class WeeklyReportStore(Protocol):
    async def upsert_reports(
        self, reports: AsyncIterable[WeeklyReportStorageRecord]
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class WeeklyReportStorageRejection:
    ward_id: int
    column: str | None
    sqlstate: str = "23502"


@dataclass(frozen=True, slots=True)
class WeeklyReportStorageResult:
    written_count: int
    skipped: tuple[WeeklyReportStorageRejection, ...]


class AsyncpgWeeklyReportStore:
    """Atomically upsert one generated bulk job in bounded DB batches."""

    def __init__(self, settings: WeeklyReportStorageSettings) -> None:
        self.settings = settings
        self._pool: asyncpg.Pool | None = None

    async def start(self) -> None:
        if self._pool is not None:
            return
        try:
            self._pool = await asyncpg.create_pool(
                dsn=self.settings.dsn,
                min_size=self.settings.min_pool_size,
                max_size=self.settings.max_pool_size,
                timeout=self.settings.connect_timeout_seconds,
                command_timeout=self.settings.command_timeout_seconds,
                server_settings={"application_name": "ax_weekly_report_storage_writer"},
            )
        except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
            raise WeeklyReportStorageUnavailable(
                "weekly-report PostgreSQL storage is unavailable"
            ) from exc

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def health(self) -> bool:
        if self._pool is None:
            return False
        try:
            async with self._pool.acquire() as connection:
                return await connection.fetchval("SELECT 1") == 1
        except (asyncpg.PostgresError, OSError, TimeoutError):
            return False

    async def upsert_reports(
        self, reports: AsyncIterable[WeeklyReportStorageRecord]
    ) -> int:
        result = await self._upsert_reports(reports, skip_not_null=False)
        return result.written_count

    async def upsert_reports_skipping_not_null(
        self, reports: AsyncIterable[WeeklyReportStorageRecord]
    ) -> WeeklyReportStorageResult:
        """Operator recovery only: skip SQLSTATE 23502 and disclose rejected wards."""
        return await self._upsert_reports(reports, skip_not_null=True)

    async def _upsert_reports(
        self,
        reports: AsyncIterable[WeeklyReportStorageRecord],
        *,
        skip_not_null: bool,
    ) -> WeeklyReportStorageResult:
        if self._pool is None:
            raise WeeklyReportStorageUnavailable(
                "weekly-report PostgreSQL storage pool is not started"
            )
        stored_count = 0
        skipped: list[WeeklyReportStorageRejection] = []
        pending: list[tuple[object, ...]] = []

        async def write_batch(connection: asyncpg.Connection) -> int:
            if not skip_not_null:
                await connection.executemany(_UPSERT_REPORT_SQL, pending)
                return len(pending)
            try:
                # Nested transactions are savepoints. Roll back the failed batch
                # before isolating its rows, keeping the outer transaction usable.
                async with connection.transaction():
                    await connection.executemany(_UPSERT_REPORT_SQL, pending)
                return len(pending)
            except asyncpg.NotNullViolationError:
                pass
            written = 0
            for parameters in pending:
                try:
                    async with connection.transaction():
                        await connection.executemany(_UPSERT_REPORT_SQL, [parameters])
                    written += 1
                except asyncpg.NotNullViolationError as exc:
                    skipped.append(
                        WeeklyReportStorageRejection(
                            ward_id=int(parameters[0]), column=exc.column_name
                        )
                    )
            return written

        try:
            async with (
                self._pool.acquire() as connection,
                connection.transaction(),
            ):
                async for report in reports:
                    pending.append(report.sql_parameters())
                    if len(pending) == self.settings.batch_size:
                        stored_count += await write_batch(connection)
                        pending.clear()
                if pending:
                    stored_count += await write_batch(connection)
        except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
            raise WeeklyReportStorageUnavailable(
                "weekly-report PostgreSQL upsert failed"
            ) from exc
        return WeeklyReportStorageResult(stored_count, tuple(skipped))


__all__ = [
    "AsyncpgWeeklyReportStore",
    "WeeklyReportStorageConfigurationError",
    "WeeklyReportStorageRecord",
    "WeeklyReportStorageSettings",
    "WeeklyReportStorageUnavailable",
    "WeeklyReportStore",
]
