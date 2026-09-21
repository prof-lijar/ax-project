"""Local transactional outbox. All payload access stays within the workflow."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from uuid import UUID, uuid4

import asyncpg

TABLE = "ansimk.weekly_report_sync_outbox"
LEASE_SECONDS = 120


def encode_payload(parameters: tuple[object, ...]) -> tuple[str, str]:
    ward, start, end, score, status, report = parameters
    payload = json.dumps(
        {
            "version": 1,
            "ward_id": ward,
            "week_start_date": str(start),
            "week_end_date": str(end),
            "weekly_score": score,
            "weekly_status": status,
            "report_data": json.loads(str(report)),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return payload, hashlib.sha256(payload.encode()).hexdigest()


async def enqueue(
    connection: asyncpg.Connection, parameters: Sequence[tuple[object, ...]]
) -> None:
    """Caller MUST own the report-write transaction on this same connection."""
    await connection.executemany(
        f"INSERT INTO {TABLE} (payload, payload_sha256) VALUES ($1, $2) "
        "ON CONFLICT (payload_sha256) DO NOTHING",
        [encode_payload(row) for row in parameters],
    )


class OutboxSchemaError(ValueError):
    """The local outbox cannot persist the worker's terminal skip state."""


class Outbox:
    def __init__(self, pool: asyncpg.Pool, max_attempts: int = 8) -> None:
        self.pool = pool
        self.max_attempts = max_attempts

    async def check(self) -> None:
        """Verify connectivity and the installed outbox columns without claiming work."""
        async with self.pool.acquire() as conn, conn.transaction(readonly=True):
            await conn.fetch(
                f"SELECT id, payload, payload_sha256, status, attempts, "
                "next_attempt_at, lease_token, lease_until, error_code, "
                f"created_at, delivered_at FROM {TABLE} LIMIT 0"
            )

            definition = await conn.fetchval(
                "SELECT pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
                "WHERE conrelid=$1::regclass "
                "AND conname='weekly_report_sync_outbox_status_check'",
                TABLE,
            )
            if not definition or "'skipped'" not in definition:
                raise OutboxSchemaError("outbox_skip_migration_missing")

    async def claim(self) -> asyncpg.Record | None:
        token = uuid4()
        async with self.pool.acquire() as conn, conn.transaction():
            # Crashes consume an attempt too. Exhausted expired leases must not loop.
            await conn.execute(
                f"UPDATE {TABLE} SET status='blocked', error_code='attempts_exhausted', "
                "lease_token=NULL, lease_until=NULL WHERE status='running' "
                "AND lease_until <= NOW() AND attempts >= $1",
                self.max_attempts,
            )
            return await conn.fetchrow(
                f"WITH candidate AS (SELECT id FROM {TABLE} WHERE "
                "attempts < $1 AND ((status='pending' AND next_attempt_at <= NOW()) "
                "OR (status='running' AND lease_until <= NOW())) "
                "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) "
                f"UPDATE {TABLE} o SET status='running', attempts=attempts+1, "
                "lease_token=$2, lease_until=NOW()+$3*INTERVAL '1 second' "
                "FROM candidate c WHERE o.id=c.id RETURNING o.*",
                self.max_attempts,
                token,
                LEASE_SECONDS,
            )

    async def finish(
        self,
        delivery_id: int,
        token: UUID,
        *,
        error_code: str | None = None,
        retryable: bool = False,
        skipped: bool = False,
    ) -> None:
        if skipped:
            if error_code is not None or retryable:
                raise ValueError("skipped delivery cannot also be failed or retryable")
            await self.pool.execute(
                f"UPDATE {TABLE} SET status='skipped', error_code='missing_ward', "
                "lease_token=NULL, lease_until=NULL, delivered_at=NULL "
                "WHERE id=$1 AND lease_token=$2 AND status='running'",
                delivery_id,
                token,
            )
            return
        await self.pool.execute(
            f"UPDATE {TABLE} SET status=CASE WHEN $3::text IS NULL THEN 'delivered' "
            "WHEN $4 AND attempts < $5 THEN 'pending' ELSE 'blocked' END, "
            "error_code=$3, lease_token=NULL, lease_until=NULL, "
            "delivered_at=CASE WHEN $3::text IS NULL THEN NOW() ELSE NULL END, "
            "next_attempt_at=NOW()+LEAST(3600, 30*POWER(2, LEAST(attempts-1, 7))) "
            "*INTERVAL '1 second' WHERE id=$1 AND lease_token=$2 AND status='running'",
            delivery_id,
            token,
            error_code,
            retryable,
            self.max_attempts,
        )

    async def retry(self, delivery_id: int) -> bool:
        result = await self.pool.execute(
            f"UPDATE {TABLE} SET status='pending', attempts=0, error_code=NULL, "
            "next_attempt_at=NOW() WHERE id=$1 AND status IN ('blocked', 'skipped')",
            delivery_id,
        )
        return result == "UPDATE 1"

    async def status(self) -> dict:
        counts = await self.pool.fetch(
            f"SELECT status, count(*) AS count FROM {TABLE} GROUP BY status"
        )
        issues = await self.pool.fetch(
            f"SELECT id, status, attempts, error_code, next_attempt_at, lease_until "
            f"FROM {TABLE} WHERE status IN ('pending', 'running', 'blocked') "
            "ORDER BY id LIMIT 100"
        )
        return {
            "counts": {row["status"]: row["count"] for row in counts},
            "outstanding": [dict(row) for row in issues],
        }

    async def preview(self, limit: int) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            f"SELECT * FROM {TABLE} WHERE status IN ('pending', 'blocked') "
            "ORDER BY id LIMIT $1",
            limit,
        )
