from typing import Any

import pytest
from ax_integrations import (
    AsyncpgReadOnlyDatabase,
    DatabaseConfigurationError,
    PostgresSettings,
)


class AsyncContext:
    def __init__(self, value: Any) -> None:
        self.value = value

    async def __aenter__(self) -> Any:
        return self.value

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.readonly: bool | None = None

    def transaction(self, *, readonly: bool) -> AsyncContext:
        self.readonly = readonly
        return AsyncContext(None)

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        assert query == "SELECT $1::int AS value"
        return [{"value": args[0]}]

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any]:
        return {"ok": 1}


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def acquire(self) -> AsyncContext:
        return AsyncContext(self.connection)


@pytest.mark.asyncio
async def test_database_fetch_uses_readonly_transaction() -> None:
    database = AsyncpgReadOnlyDatabase(
        PostgresSettings(dsn="postgresql://example.invalid/ansimk")
    )
    connection = FakeConnection()
    database._pool = FakePool(connection)  # type: ignore[assignment]

    rows = await database.fetch("SELECT $1::int AS value", 7)

    assert rows == [{"value": 7}]
    assert connection.readonly is True


def test_database_settings_reject_missing_dsn_and_unbounded_pool() -> None:
    with pytest.raises(DatabaseConfigurationError, match="DSN"):
        PostgresSettings.from_env({})
    with pytest.raises(DatabaseConfigurationError, match="too large"):
        PostgresSettings(dsn="postgresql://example.invalid/db", max_pool_size=51)
