import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from workflows.daily_risk_counts.workflow import day_bounds, previous_day, reconcile_day


@pytest.mark.parametrize(
    "now,expected",
    [
        (datetime(2026, 10, 25, 20, 15, tzinfo=UTC), date(2026, 10, 25)),
        (datetime(2026, 1, 1, 0, tzinfo=UTC), date(2025, 12, 31)),
        (datetime(2024, 3, 1, 0, tzinfo=UTC), date(2024, 2, 29)),
        (datetime(2026, 10, 25, 14, 59, tzinfo=UTC), date(2026, 10, 24)),
    ],
)
def test_previous_local_day(now, expected):
    assert previous_day(now) == expected


def test_naive_now_rejected():
    with pytest.raises(ValueError):
        previous_day(datetime(2026, 10, 26))  # noqa: DTZ001 -- verify naive rejection


def test_full_day_bounds_include_midnight_and_last_minute():
    start, end = day_bounds(date(2026, 10, 31))
    assert start.astimezone(UTC) == datetime(2026, 10, 30, 15, tzinfo=UTC)
    assert end.astimezone(UTC) == datetime(2026, 10, 31, 15, tzinfo=UTC)
    assert start.hour == end.hour == 0
    assert end.date() == date(2026, 11, 1)


def connection_fixture():
    connection = AsyncMock()
    transaction = AsyncMock()
    connection.transaction = MagicMock(return_value=transaction)
    connection.fetchrow.return_value = {"wards": 3, "inserts": 1, "updates": 1}
    connection.fetchval.return_value = 2
    return connection, transaction


@pytest.mark.asyncio
async def test_preview_cannot_write():
    connection, _ = connection_fixture()
    result = await reconcile_day(connection, date(2026, 1, 1))
    assert result["mode"] == "preview"
    assert result["unchanged"] == 1
    connection.transaction.assert_called_once_with(
        isolation="repeatable_read", readonly=True
    )
    connection.fetchval.assert_not_awaited()
    assert not any("LOCK TABLE" in c.args[0] for c in connection.execute.call_args_list)


@pytest.mark.asyncio
async def test_commit_failure_cannot_return_success():
    connection, transaction = connection_fixture()
    transaction.__aexit__.side_effect = RuntimeError("commit failed")
    with pytest.raises(RuntimeError, match="commit failed"):
        await reconcile_day(connection, date(2026, 1, 1), apply=True)


@pytest.mark.asyncio
async def test_write_mismatch_rolls_back():
    connection, _ = connection_fixture()
    connection.fetchval.return_value = 0
    with pytest.raises(RuntimeError, match="Write count mismatch"):
        await reconcile_day(connection, date(2026, 1, 1), apply=True)


@pytest.mark.asyncio
async def test_apply_contract_and_lock_precedes_source_snapshot():
    connection, _ = connection_fixture()
    result = await reconcile_day(connection, date(2026, 1, 1), apply=True)
    assert result["month"] == "2026.01"
    assert result["written"] == 2
    calls = connection.mock_calls
    lock = next(
        i
        for i, c in enumerate(calls)
        if c[0] == "execute" and "LOCK TABLE" in c.args[0]
    )
    read = next(i for i, c in enumerate(calls) if c[0] == "fetchrow")
    assert lock < read
    assert connection.fetchrow.call_args.args[-1] == 1


@pytest.mark.asyncio
async def test_incomplete_day_rejected_without_database_calls():
    connection, _ = connection_fixture()
    with pytest.raises(ValueError):
        await reconcile_day(connection, date(9999, 1, 1), apply=True)
    assert connection.mock_calls == []


def test_cli_sanitizes_connection_failure(monkeypatch, capsys):
    from apps.daily_risk_scheduler import run

    monkeypatch.setattr(run, "database_dsn", lambda: "postgresql://user:SECRET@host/db")
    monkeypatch.setattr(
        run.asyncpg, "connect", AsyncMock(side_effect=RuntimeError("SECRET"))
    )
    assert run.main(["--date", "2026-01-01"]) == 1
    output = capsys.readouterr().out
    assert "SECRET" not in output
    assert json.loads(output.splitlines()[-1])["event"] == "daily_risk_failed"
