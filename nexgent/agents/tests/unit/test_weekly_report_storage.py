from contextlib import asynccontextmanager
from datetime import date
from typing import Any

import asyncpg
import pytest

from workflows.weekly_report.bulk.report_store import (
    AsyncpgWeeklyReportStore,
    WeeklyReportStorageConfigurationError,
    WeeklyReportStorageRecord,
    WeeklyReportStorageSettings,
    WeeklyReportStorageUnavailable,
)


class AsyncContext:
    def __init__(self, value: Any) -> None:
        self.value = value
        self.entered = 0
        self.exited = 0

    async def __aenter__(self) -> Any:
        self.entered += 1
        return self.value

    async def __aexit__(self, *args: object) -> None:
        self.exited += 1


class FakeConnection:
    def __init__(self) -> None:
        self.transaction_context = AsyncContext(None)
        self.calls: list[tuple[str, list[tuple[object, ...]]]] = []

    def transaction(self) -> AsyncContext:
        return self.transaction_context

    async def executemany(self, query: str, values: list[tuple[object, ...]]) -> None:
        self.calls.append((query, list(values)))


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.acquire_context = AsyncContext(connection)

    def acquire(self) -> AsyncContext:
        return self.acquire_context


def _record(ward_id: int) -> WeeklyReportStorageRecord:
    return WeeklyReportStorageRecord(
        ward_id=ward_id,
        week_start_date=date(2026, 8, 3),
        week_end_date=date(2026, 8, 9),
        weekly_score=93,
        weekly_status="GOOD",
        report_data_json='{"template_version":"weekly-report-v5"}',
    )


@pytest.mark.asyncio
async def test_storage_upserts_more_than_six_thousand_reports_atomically_in_batches() -> (
    None
):
    report_store = AsyncpgWeeklyReportStore(
        WeeklyReportStorageSettings(
            dsn="postgresql://example.invalid/ansimk", batch_size=500
        )
    )
    connection = FakeConnection()
    pool = FakePool(connection)
    report_store._pool = pool  # type: ignore[assignment]

    async def records():
        for ward_id in range(1, 6_002):
            yield _record(ward_id)

    stored_count = await report_store.upsert_reports(records())

    assert stored_count == 6_001
    assert [len(values) for _, values in connection.calls] == [500] * 12 + [1]
    assert connection.transaction_context.entered == 1
    assert connection.transaction_context.exited == 1
    assert pool.acquire_context.entered == 1
    assert pool.acquire_context.exited == 1
    query = connection.calls[0][0]
    assert "INSERT INTO ansimk.resources_ward_weekly_report" in query
    assert "ON CONFLICT (ward_id, week_start_date) DO UPDATE" in query
    assert "report_data = EXCLUDED.report_data" in query
    assert "updated_at = NOW()" in query
    insert, update = query.split("ON CONFLICT", 1)
    assert "created_at" in insert and "updated_at" in insert
    assert "$6::jsonb, NOW(), NOW()" in insert
    assert "created_at" not in update


def test_storage_settings_require_a_dedicated_bounded_writer() -> None:
    with pytest.raises(WeeklyReportStorageConfigurationError, match="DSN"):
        WeeklyReportStorageSettings.from_env({})
    with pytest.raises(WeeklyReportStorageConfigurationError, match="batch size"):
        WeeklyReportStorageSettings(
            dsn="postgresql://example.invalid/ansimk", batch_size=1_001
        )
    with pytest.raises(WeeklyReportStorageConfigurationError, match="pool size"):
        WeeklyReportStorageSettings(
            dsn="postgresql://example.invalid/ansimk",
            min_pool_size=3,
            max_pool_size=2,
        )


def test_storage_settings_can_reuse_the_existing_ansimk_dsn() -> None:
    settings = WeeklyReportStorageSettings.from_env(
        {"ANSIMK_DATABASE_DSN": "postgresql://current-role@example.invalid/ansimk"}
    )

    assert settings.dsn == "postgresql://current-role@example.invalid/ansimk"


class TransactionalConnection:
    """Model transaction abort/savepoint rollback, including earlier batch rows."""

    def __init__(self, rejected, fatal=None):
        self.rows = []
        self.aborted = False
        self.rejected = rejected
        self.fatal = fatal

    @asynccontextmanager
    async def transaction(self):
        snapshot = list(self.rows)
        previous_aborted = self.aborted
        try:
            yield
        except BaseException:
            self.rows = snapshot
            self.aborted = previous_aborted
            raise

    async def executemany(self, query, values):
        assert not self.aborted, "failed transaction was not rolled back"
        for row in values:
            if row[0] == self.fatal:
                self.aborted = True
                raise asyncpg.InsufficientPrivilegeError("private diagnostic")
            if row[0] in self.rejected:
                self.aborted = True
                error = asyncpg.NotNullViolationError("private report content")
                error.column_name = "weekly_score"
                raise error
            self.rows.append(row[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("rejected", [{2}, {1, 2, 3, 4}, set()])
async def test_recovery_skip_isolates_bad_rows_and_continues_batches(rejected):
    connection = TransactionalConnection(rejected)
    store = AsyncpgWeeklyReportStore(
        WeeklyReportStorageSettings(dsn="postgresql://test", batch_size=3)
    )
    store._pool = FakePool(connection)

    async def records():
        for ward_id in range(1, 5):
            yield _record(ward_id)

    result = await store.upsert_reports_skipping_not_null(records())
    assert connection.rows == [i for i in range(1, 5) if i not in rejected]
    assert result.written_count == 4 - len(rejected)
    assert {item.ward_id for item in result.skipped} == rejected
    assert all(item.column == "weekly_score" for item in result.skipped)
    assert "private report content" not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "skip, fatal, artifact_failure",
    [
        (False, None, False),
        (True, 4, False),
        (True, None, True),
    ],
)
async def test_recovery_does_not_ignore_other_errors_or_change_default(
    skip, fatal, artifact_failure
):
    connection = TransactionalConnection({2}, fatal=fatal)
    store = AsyncpgWeeklyReportStore(
        WeeklyReportStorageSettings(dsn="postgresql://test", batch_size=2)
    )
    store._pool = FakePool(connection)

    async def records():
        for ward_id in range(1, 5):
            yield _record(ward_id)
        if artifact_failure:
            raise ValueError("checksum mismatch")

    method = store.upsert_reports_skipping_not_null if skip else store.upsert_reports
    error = ValueError if artifact_failure else WeeklyReportStorageUnavailable
    with pytest.raises(error):
        await method(records())
    assert connection.rows == []
