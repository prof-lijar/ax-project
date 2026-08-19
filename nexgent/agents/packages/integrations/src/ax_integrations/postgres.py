"""Reusable pooled, read-only PostgreSQL integration."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import asyncpg


class ReadOnlyDatabase(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def health(self) -> bool: ...

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]: ...

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None: ...


class DatabaseConfigurationError(ValueError):
    """Safe invalid database configuration error."""


class DatabaseUnavailable(RuntimeError):
    """Safe database availability error without connection details."""


@dataclass(frozen=True, slots=True)
class PostgresSettings:
    dsn: str = field(repr=False)
    min_pool_size: int = 1
    max_pool_size: int = 5
    connect_timeout_seconds: float = 10.0
    command_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.dsn:
            raise DatabaseConfigurationError("ANSIMK_DATABASE_DSN must not be empty")
        if self.min_pool_size < 1 or self.max_pool_size < self.min_pool_size:
            raise DatabaseConfigurationError("database pool sizes are invalid")
        if self.max_pool_size > 50:
            raise DatabaseConfigurationError("database maximum pool size is too large")
        if self.connect_timeout_seconds <= 0 or self.command_timeout_seconds <= 0:
            raise DatabaseConfigurationError("database timeouts must be positive")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> PostgresSettings:
        values = os.environ if environ is None else environ
        try:
            return cls(
                dsn=values.get("ANSIMK_DATABASE_DSN", ""),
                min_pool_size=int(values.get("ANSIMK_DATABASE_MIN_POOL_SIZE", "1")),
                max_pool_size=int(values.get("ANSIMK_DATABASE_MAX_POOL_SIZE", "5")),
                connect_timeout_seconds=float(
                    values.get("ANSIMK_DATABASE_CONNECT_TIMEOUT_SECONDS", "10")
                ),
                command_timeout_seconds=float(
                    values.get("ANSIMK_DATABASE_COMMAND_TIMEOUT_SECONDS", "30")
                ),
            )
        except DatabaseConfigurationError:
            raise
        except ValueError as exc:
            raise DatabaseConfigurationError(
                "database numeric configuration is invalid"
            ) from exc


class AsyncpgReadOnlyDatabase:
    """One process-wide asyncpg pool whose calls run in read-only transactions."""

    def __init__(self, settings: PostgresSettings) -> None:
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
                server_settings={"application_name": "ax_weekly_report_source"},
            )
        except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
            raise DatabaseUnavailable("PostgreSQL is unavailable") from exc

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def health(self) -> bool:
        try:
            row = await self.fetchrow("SELECT 1 AS ok")
        except DatabaseUnavailable:
            return False
        return row == {"ok": 1}

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        records = await self._execute("fetch", query, args)
        return [dict(record) for record in records]

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        record = await self._execute("fetchrow", query, args)
        return dict(record) if record is not None else None

    async def _execute(
        self,
        operation: str,
        query: str,
        args: Sequence[object],
    ) -> Any:
        if self._pool is None:
            raise DatabaseUnavailable("PostgreSQL pool is not started")
        try:
            async with (
                self._pool.acquire() as connection,
                connection.transaction(readonly=True),
            ):
                method = getattr(connection, operation)
                return await method(query, *args)
        except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
            raise DatabaseUnavailable("PostgreSQL query failed") from exc
