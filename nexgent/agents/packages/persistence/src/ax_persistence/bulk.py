"""Generic PostgreSQL-leased jobs used by high-volume workflow workers."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

import asyncpg


class BulkStoreError(RuntimeError):
    """Safe durable-job storage failure."""


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class BulkJobRecord:
    job_id: UUID
    job_kind: str
    idempotency_key: str
    request: dict[str, Any]
    status: str
    cursor: str | None = None
    producer_done: bool = False
    selection_truncated: bool = False
    next_cursor: str | None = None
    warnings: tuple[str, ...] = ()
    cancel_requested: bool = False
    export_uri: str | None = None
    export_checksum: str | None = None
    finalizer_owner: str | None = None
    finalizer_lease_expires_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class BulkItemRecord:
    job_id: UUID
    item_key: str
    payload_uri: str
    payload_checksum: str
    status: str = "pending"
    attempt_count: int = 0
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    output_uri: str | None = None
    output_checksum: str | None = None
    generation_mode: str | None = None
    error_code: str | None = None


class BulkJobStore(Protocol):
    async def create_job(
        self, job_kind: str, idempotency_key: str, request: Mapping[str, Any]
    ) -> BulkJobRecord: ...
    async def get_job(self, job_id: UUID) -> BulkJobRecord: ...
    async def list_jobs(self, job_kind: str, limit: int = 20) -> list[BulkJobRecord]: ...
    async def next_job(self, job_kind: str) -> BulkJobRecord | None: ...
    async def set_job_status(self, job_id: UUID, status: str) -> None: ...
    async def claim_producer(
        self, job_id: UUID, owner: str, lease_seconds: int
    ) -> bool: ...
    async def heartbeat_producer(
        self, job_id: UUID, owner: str, lease_seconds: int
    ) -> None: ...
    async def stage_items(
        self, job_id: UUID, items: list[BulkItemRecord], cursor: str | None
    ) -> None: ...
    async def finish_producer(
        self,
        job_id: UUID,
        *,
        next_cursor: str | None,
        selection_truncated: bool,
        warnings: list[str],
    ) -> None: ...
    async def claim_items(
        self, job_id: UUID, owner: str, limit: int, lease_seconds: int
    ) -> list[BulkItemRecord]: ...
    async def complete_item(
        self,
        job_id: UUID,
        item_key: str,
        owner: str,
        *,
        output_uri: str,
        output_checksum: str,
        generation_mode: str,
    ) -> None: ...
    async def fail_item(
        self,
        job_id: UUID,
        item_key: str,
        owner: str,
        error_code: str,
        max_attempts: int,
    ) -> None: ...
    async def list_items(self, job_id: UUID) -> list[BulkItemRecord]: ...
    async def item_counts(self, job_id: UUID) -> dict[str, int]: ...
    async def request_cancel(self, job_id: UUID) -> None: ...
    async def cancel_pending_items(self, job_id: UUID) -> None: ...
    async def try_start_finalizer(
        self, job_id: UUID, owner: str, lease_seconds: int
    ) -> bool: ...
    async def finish_job(
        self,
        job_id: UUID,
        *,
        status: str,
        export_uri: str,
        export_checksum: str,
        expires_at: datetime,
    ) -> None: ...
    async def expire_jobs(self, before: datetime) -> list[UUID]: ...


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ax_bulk_jobs (
    job_id uuid PRIMARY KEY,
    job_kind text NOT NULL,
    idempotency_key text NOT NULL,
    request jsonb NOT NULL,
    status text NOT NULL,
    cursor text,
    producer_done boolean NOT NULL DEFAULT false,
    producer_owner text,
    producer_lease_expires_at timestamptz,
    selection_truncated boolean NOT NULL DEFAULT false,
    next_cursor text,
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    cancel_requested boolean NOT NULL DEFAULT false,
    export_uri text,
    export_checksum text,
    finalizer_owner text,
    finalizer_lease_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    UNIQUE (job_kind, idempotency_key)
);
CREATE TABLE IF NOT EXISTS ax_bulk_items (
    job_id uuid NOT NULL REFERENCES ax_bulk_jobs(job_id) ON DELETE CASCADE,
    item_key text NOT NULL,
    payload_uri text NOT NULL,
    payload_checksum text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    attempt_count integer NOT NULL DEFAULT 0,
    lease_owner text,
    lease_expires_at timestamptz,
    output_uri text,
    output_checksum text,
    generation_mode text,
    error_code text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, item_key)
);
CREATE INDEX IF NOT EXISTS ax_bulk_items_claim_idx
    ON ax_bulk_items (job_id, status, item_key);
ALTER TABLE ax_bulk_jobs ADD COLUMN IF NOT EXISTS finalizer_owner text;
ALTER TABLE ax_bulk_jobs ADD COLUMN IF NOT EXISTS finalizer_lease_expires_at timestamptz;
"""


class AsyncpgBulkJobStore:
    def __init__(
        self, dsn: str, *, min_pool_size: int = 1, max_pool_size: int = 10
    ) -> None:
        if not dsn:
            raise ValueError("WEEKLY_REPORT_JOB_DATABASE_DSN must not be empty")
        if min_pool_size < 1 or not min_pool_size <= max_pool_size <= 50:
            raise ValueError("bulk job database pool sizes are invalid")
        self._dsn = dsn
        self._min_pool_size = min_pool_size
        self._max_pool_size = max_pool_size
        self._pool: asyncpg.Pool | None = None

    async def start(self) -> None:
        if self._pool is not None:
            return
        try:
            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=self._min_pool_size,
                max_size=self._max_pool_size,
                server_settings={"application_name": "ax_weekly_report_bulk"},
            )
            async with self._pool.acquire() as connection:
                await connection.execute(SCHEMA_SQL)
        except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
            if self._pool is not None:
                await self._pool.close()
                self._pool = None
            raise BulkStoreError("bulk job database is unavailable") from exc

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def create_job(
        self, job_kind: str, idempotency_key: str, request: Mapping[str, Any]
    ) -> BulkJobRecord:
        pool = self._required_pool()
        job_id = uuid4()
        try:
            row = await pool.fetchrow(
                """
                INSERT INTO ax_bulk_jobs(job_id, job_kind, idempotency_key, request, status)
                VALUES($1, $2, $3, $4::jsonb, 'pending')
                ON CONFLICT(job_kind, idempotency_key) DO UPDATE
                    SET updated_at = ax_bulk_jobs.updated_at
                RETURNING *
                """,
                job_id,
                job_kind,
                idempotency_key,
                json.dumps(dict(request)),
            )
            job = _job(row)
            if job.request != dict(request):
                raise BulkStoreError("bulk idempotency key was already used")
            return job
        except asyncpg.PostgresError as exc:
            raise BulkStoreError("bulk job could not be created") from exc

    async def get_job(self, job_id: UUID) -> BulkJobRecord:
        try:
            row = await self._required_pool().fetchrow(
                "SELECT * FROM ax_bulk_jobs WHERE job_id=$1", job_id
            )
        except asyncpg.PostgresError as exc:
            raise BulkStoreError("bulk job could not be loaded") from exc
        if row is None:
            raise BulkStoreError("bulk job was not found")
        return _job(row)

    async def list_jobs(
        self, job_kind: str, limit: int = 20
    ) -> list[BulkJobRecord]:
        if not 1 <= limit <= 100:
            raise ValueError("bulk job list limit must be between 1 and 100")
        try:
            rows = await self._required_pool().fetch(
                """
                SELECT * FROM ax_bulk_jobs
                WHERE job_kind=$1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                job_kind,
                limit,
            )
        except asyncpg.PostgresError as exc:
            raise BulkStoreError("bulk jobs could not be loaded") from exc
        return [_job(row) for row in rows]

    async def next_job(self, job_kind: str) -> BulkJobRecord | None:
        try:
            row = await self._required_pool().fetchrow(
                """
                SELECT * FROM ax_bulk_jobs
                WHERE job_kind=$1 AND status IN ('pending','preparing','running','finalizing','cancelling')
                ORDER BY created_at LIMIT 1
                """,
                job_kind,
            )
        except asyncpg.PostgresError as exc:
            raise BulkStoreError("bulk job queue could not be loaded") from exc
        return _job(row) if row else None

    async def set_job_status(self, job_id: UUID, status: str) -> None:
        await self._execute(
            "UPDATE ax_bulk_jobs SET status=$2, updated_at=now() WHERE job_id=$1",
            job_id,
            status,
        )

    async def claim_producer(
        self, job_id: UUID, owner: str, lease_seconds: int
    ) -> bool:
        result = await self._execute(
            """
            UPDATE ax_bulk_jobs SET producer_owner=$2,
                producer_lease_expires_at=now()+($3 * interval '1 second'),
                status=CASE WHEN status='pending' THEN 'preparing' ELSE status END,
                updated_at=now()
            WHERE job_id=$1 AND NOT producer_done
              AND (producer_lease_expires_at IS NULL OR producer_lease_expires_at < now()
                   OR producer_owner=$2)
            """,
            job_id,
            owner,
            lease_seconds,
        )
        return result.endswith(" 1")

    async def heartbeat_producer(
        self, job_id: UUID, owner: str, lease_seconds: int
    ) -> None:
        await self._execute(
            """
            UPDATE ax_bulk_jobs SET producer_lease_expires_at=now()+($3 * interval '1 second'),
                updated_at=now() WHERE job_id=$1 AND producer_owner=$2 AND NOT producer_done
            """,
            job_id,
            owner,
            lease_seconds,
        )

    async def stage_items(
        self, job_id: UUID, items: list[BulkItemRecord], cursor: str | None
    ) -> None:
        pool = self._required_pool()
        try:
            async with pool.acquire() as connection, connection.transaction():
                for item in items:
                    await connection.execute(
                        """
                        INSERT INTO ax_bulk_items(
                            job_id,item_key,payload_uri,payload_checksum,status
                        ) VALUES($1,$2,$3,$4,'pending')
                        ON CONFLICT(job_id,item_key) DO NOTHING
                        """,
                        job_id,
                        item.item_key,
                        item.payload_uri,
                        item.payload_checksum,
                    )
                await connection.execute(
                    "UPDATE ax_bulk_jobs SET cursor=$2,status='running',updated_at=now() WHERE job_id=$1",
                    job_id,
                    cursor,
                )
        except asyncpg.PostgresError as exc:
            raise BulkStoreError("bulk work items could not be staged") from exc

    async def finish_producer(
        self,
        job_id: UUID,
        *,
        next_cursor: str | None,
        selection_truncated: bool,
        warnings: list[str],
    ) -> None:
        await self._execute(
            """
            UPDATE ax_bulk_jobs SET producer_done=true, producer_owner=NULL,
                producer_lease_expires_at=NULL, selection_truncated=$2,
                next_cursor=$3, warnings=$4::jsonb, status='running', updated_at=now()
            WHERE job_id=$1
            """,
            job_id,
            selection_truncated,
            next_cursor,
            json.dumps(sorted(set(warnings))),
        )

    async def claim_items(
        self, job_id: UUID, owner: str, limit: int, lease_seconds: int
    ) -> list[BulkItemRecord]:
        pool = self._required_pool()
        try:
            rows = await pool.fetch(
                """
                WITH candidates AS (
                    SELECT item_key FROM ax_bulk_items
                    WHERE job_id=$1 AND (
                        status='pending' OR (status='leased' AND lease_expires_at < now())
                    )
                    ORDER BY item_key FOR UPDATE SKIP LOCKED LIMIT $3
                )
                UPDATE ax_bulk_items i SET status='leased', lease_owner=$2,
                    lease_expires_at=now()+($4 * interval '1 second'),
                    attempt_count=i.attempt_count+1, updated_at=now()
                FROM candidates c
                WHERE i.job_id=$1 AND i.item_key=c.item_key
                RETURNING i.*
                """,
                job_id,
                owner,
                limit,
                lease_seconds,
            )
            return [_item(row) for row in rows]
        except asyncpg.PostgresError as exc:
            raise BulkStoreError("bulk work items could not be claimed") from exc

    async def complete_item(
        self,
        job_id: UUID,
        item_key: str,
        owner: str,
        *,
        output_uri: str,
        output_checksum: str,
        generation_mode: str,
    ) -> None:
        await self._execute(
            """
            UPDATE ax_bulk_items SET status='completed',output_uri=$4,output_checksum=$5,
                generation_mode=$6,error_code=NULL,lease_owner=NULL,lease_expires_at=NULL,
                updated_at=now()
            WHERE job_id=$1 AND item_key=$2 AND lease_owner=$3 AND status='leased'
            """,
            job_id,
            item_key,
            owner,
            output_uri,
            output_checksum,
            generation_mode,
        )

    async def fail_item(
        self,
        job_id: UUID,
        item_key: str,
        owner: str,
        error_code: str,
        max_attempts: int,
    ) -> None:
        await self._execute(
            """
            UPDATE ax_bulk_items SET status=CASE WHEN attempt_count >= $5 THEN 'failed'
                    ELSE 'pending' END,
                error_code=$4,lease_owner=NULL,lease_expires_at=NULL,updated_at=now()
            WHERE job_id=$1 AND item_key=$2 AND lease_owner=$3 AND status='leased'
            """,
            job_id,
            item_key,
            owner,
            error_code,
            max_attempts,
        )

    async def list_items(self, job_id: UUID) -> list[BulkItemRecord]:
        try:
            rows = await self._required_pool().fetch(
                "SELECT * FROM ax_bulk_items WHERE job_id=$1 ORDER BY item_key",
                job_id,
            )
        except asyncpg.PostgresError as exc:
            raise BulkStoreError("bulk work items could not be loaded") from exc
        return [_item(row) for row in rows]

    async def item_counts(self, job_id: UUID) -> dict[str, int]:
        try:
            rows = await self._required_pool().fetch(
                "SELECT status,generation_mode,count(*) AS count FROM ax_bulk_items WHERE job_id=$1 GROUP BY status,generation_mode",
                job_id,
            )
        except asyncpg.PostgresError as exc:
            raise BulkStoreError("bulk work item counts could not be loaded") from exc
        counts: Counter[str] = Counter()
        for row in rows:
            counts[str(row["status"])] += int(row["count"])
            if row["generation_mode"] == "template_fallback":
                counts["fallback"] += int(row["count"])
        return dict(counts)

    async def request_cancel(self, job_id: UUID) -> None:
        await self._execute(
            "UPDATE ax_bulk_jobs SET cancel_requested=true,status='cancelling',updated_at=now() WHERE job_id=$1 AND status NOT IN ('completed','partial','failed','cancelled','expired')",
            job_id,
        )

    async def cancel_pending_items(self, job_id: UUID) -> None:
        await self._execute(
            """
            UPDATE ax_bulk_items
            SET status='cancelled', lease_owner=NULL, lease_expires_at=NULL,
                error_code='cancelled', updated_at=now()
            WHERE job_id=$1 AND status IN ('pending', 'leased')
            """,
            job_id,
        )

    async def try_start_finalizer(
        self, job_id: UUID, owner: str, lease_seconds: int
    ) -> bool:
        result = await self._execute(
            """
            UPDATE ax_bulk_jobs SET status='finalizing',finalizer_owner=$2,
                finalizer_lease_expires_at=now()+($3 * interval '1 second'),
                updated_at=now()
            WHERE job_id=$1 AND producer_done
              AND (status IN ('running','cancelling') OR
                   (status='finalizing' AND
                    (finalizer_lease_expires_at < now() OR finalizer_owner=$2)))
              AND NOT EXISTS (SELECT 1 FROM ax_bulk_items WHERE job_id=$1 AND status IN ('pending','leased'))
            """,
            job_id,
            owner,
            lease_seconds,
        )
        return result.endswith(" 1")

    async def finish_job(
        self,
        job_id: UUID,
        *,
        status: str,
        export_uri: str,
        export_checksum: str,
        expires_at: datetime,
    ) -> None:
        await self._execute(
            """
            UPDATE ax_bulk_jobs SET status=$2,export_uri=$3,export_checksum=$4,
                expires_at=$5,finalizer_owner=NULL,finalizer_lease_expires_at=NULL,
                updated_at=now() WHERE job_id=$1
            """,
            job_id,
            status,
            export_uri,
            export_checksum,
            expires_at,
        )

    async def expire_jobs(self, before: datetime) -> list[UUID]:
        pool = self._required_pool()
        try:
            async with pool.acquire() as connection, connection.transaction():
                rows = await connection.fetch(
                    """
                    UPDATE ax_bulk_jobs SET status='expired',export_uri=NULL,export_checksum=NULL,
                        updated_at=now() WHERE expires_at IS NOT NULL AND expires_at <= $1
                        AND status IN ('completed','partial','cancelled') RETURNING job_id
                    """,
                    before,
                )
                job_ids = [row["job_id"] for row in rows]
                if job_ids:
                    await connection.execute(
                        "DELETE FROM ax_bulk_items WHERE job_id=ANY($1::uuid[])",
                        job_ids,
                    )
        except asyncpg.PostgresError as exc:
            raise BulkStoreError("expired bulk jobs could not be cleaned") from exc
        return job_ids

    async def _execute(self, query: str, *args: object) -> str:
        try:
            return await self._required_pool().execute(query, *args)
        except asyncpg.PostgresError as exc:
            raise BulkStoreError("bulk job database operation failed") from exc

    def _required_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise BulkStoreError("bulk job database is not started")
        return self._pool


class InMemoryBulkJobStore:
    """Deterministic test store with the same lease and idempotency rules."""

    def __init__(self) -> None:
        self.jobs: dict[UUID, BulkJobRecord] = {}
        self.items: dict[tuple[UUID, str], BulkItemRecord] = {}
        self._lock = asyncio.Lock()

    async def create_job(
        self, job_kind: str, idempotency_key: str, request: Mapping[str, Any]
    ) -> BulkJobRecord:
        async with self._lock:
            for job in self.jobs.values():
                if (job.job_kind, job.idempotency_key) == (job_kind, idempotency_key):
                    if job.request != dict(request):
                        raise BulkStoreError("bulk idempotency key was already used")
                    return job
            job = BulkJobRecord(
                uuid4(), job_kind, idempotency_key, dict(request), "pending"
            )
            self.jobs[job.job_id] = job
            return job

    async def get_job(self, job_id: UUID) -> BulkJobRecord:
        try:
            return self.jobs[job_id]
        except KeyError as exc:
            raise BulkStoreError("bulk job was not found") from exc

    async def list_jobs(
        self, job_kind: str, limit: int = 20
    ) -> list[BulkJobRecord]:
        if not 1 <= limit <= 100:
            raise ValueError("bulk job list limit must be between 1 and 100")
        jobs = [job for job in self.jobs.values() if job.job_kind == job_kind]
        return sorted(jobs, key=lambda job: job.created_at, reverse=True)[:limit]

    async def next_job(self, job_kind: str) -> BulkJobRecord | None:
        jobs = [
            j
            for j in self.jobs.values()
            if j.job_kind == job_kind
            and j.status
            in {"pending", "preparing", "running", "finalizing", "cancelling"}
        ]
        return min(jobs, key=lambda job: job.created_at) if jobs else None

    async def set_job_status(self, job_id: UUID, status: str) -> None:
        self._replace_job(job_id, status=status)

    async def claim_producer(
        self, job_id: UUID, owner: str, lease_seconds: int
    ) -> bool:
        job = await self.get_job(job_id)
        if job.producer_done:
            return False
        self._replace_job(
            job_id, status="preparing" if job.status == "pending" else job.status
        )
        return True

    async def heartbeat_producer(
        self, job_id: UUID, owner: str, lease_seconds: int
    ) -> None:
        await self.get_job(job_id)

    async def stage_items(
        self, job_id: UUID, items: list[BulkItemRecord], cursor: str | None
    ) -> None:
        for item in items:
            self.items.setdefault((job_id, item.item_key), item)
        self._replace_job(job_id, cursor=cursor, status="running")

    async def finish_producer(
        self,
        job_id: UUID,
        *,
        next_cursor: str | None,
        selection_truncated: bool,
        warnings: list[str],
    ) -> None:
        self._replace_job(
            job_id,
            producer_done=True,
            next_cursor=next_cursor,
            selection_truncated=selection_truncated,
            warnings=tuple(sorted(set(warnings))),
            status="running",
        )

    async def claim_items(
        self, job_id: UUID, owner: str, limit: int, lease_seconds: int
    ) -> list[BulkItemRecord]:
        now = utc_now()
        claimed: list[BulkItemRecord] = []
        async with self._lock:
            for key in sorted(self.items):
                item = self.items[key]
                if item.job_id != job_id or not (
                    item.status == "pending"
                    or (
                        item.status == "leased"
                        and item.lease_expires_at
                        and item.lease_expires_at < now
                    )
                ):
                    continue
                updated = _replace_item(
                    item,
                    status="leased",
                    attempt_count=item.attempt_count + 1,
                    lease_owner=owner,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                )
                self.items[key] = updated
                claimed.append(updated)
                if len(claimed) == limit:
                    break
        return claimed

    async def complete_item(
        self,
        job_id: UUID,
        item_key: str,
        owner: str,
        *,
        output_uri: str,
        output_checksum: str,
        generation_mode: str,
    ) -> None:
        item = self.items[(job_id, item_key)]
        if item.lease_owner != owner:
            return
        self.items[(job_id, item_key)] = _replace_item(
            item,
            status="completed",
            output_uri=output_uri,
            output_checksum=output_checksum,
            generation_mode=generation_mode,
            lease_owner=None,
            lease_expires_at=None,
            error_code=None,
        )

    async def fail_item(
        self,
        job_id: UUID,
        item_key: str,
        owner: str,
        error_code: str,
        max_attempts: int,
    ) -> None:
        item = self.items[(job_id, item_key)]
        if item.lease_owner != owner:
            return
        self.items[(job_id, item_key)] = _replace_item(
            item,
            status="failed" if item.attempt_count >= max_attempts else "pending",
            error_code=error_code,
            lease_owner=None,
            lease_expires_at=None,
        )

    async def list_items(self, job_id: UUID) -> list[BulkItemRecord]:
        return [self.items[key] for key in sorted(self.items) if key[0] == job_id]

    async def item_counts(self, job_id: UUID) -> dict[str, int]:
        counts: Counter[str] = Counter(
            item.status for item in await self.list_items(job_id)
        )
        counts["fallback"] = sum(
            item.generation_mode == "template_fallback"
            for item in await self.list_items(job_id)
        )
        return dict(counts)

    async def request_cancel(self, job_id: UUID) -> None:
        self._replace_job(job_id, cancel_requested=True, status="cancelling")

    async def cancel_pending_items(self, job_id: UUID) -> None:
        for key, item in list(self.items.items()):
            if item.job_id == job_id and item.status in {"pending", "leased"}:
                self.items[key] = _replace_item(
                    item,
                    status="cancelled",
                    lease_owner=None,
                    lease_expires_at=None,
                    error_code="cancelled",
                )

    async def try_start_finalizer(
        self, job_id: UUID, owner: str, lease_seconds: int
    ) -> bool:
        job = await self.get_job(job_id)
        counts = await self.item_counts(job_id)
        lease_expired = (
            job.finalizer_lease_expires_at is not None
            and job.finalizer_lease_expires_at < utc_now()
        )
        can_claim = job.status in {"running", "cancelling"} or (
            job.status == "finalizing"
            and (lease_expired or job.finalizer_owner == owner)
        )
        if (
            job.producer_done
            and not counts.get("pending")
            and not counts.get("leased")
            and can_claim
        ):
            self._replace_job(
                job_id,
                status="finalizing",
                finalizer_owner=owner,
                finalizer_lease_expires_at=utc_now() + timedelta(seconds=lease_seconds),
            )
            return True
        return False

    async def finish_job(
        self,
        job_id: UUID,
        *,
        status: str,
        export_uri: str,
        export_checksum: str,
        expires_at: datetime,
    ) -> None:
        self._replace_job(
            job_id,
            status=status,
            export_uri=export_uri,
            export_checksum=export_checksum,
            expires_at=expires_at,
            finalizer_owner=None,
            finalizer_lease_expires_at=None,
        )

    async def expire_jobs(self, before: datetime) -> list[UUID]:
        expired = []
        for job in list(self.jobs.values()):
            if (
                job.expires_at
                and job.expires_at <= before
                and job.status in {"completed", "partial", "cancelled"}
            ):
                self._replace_job(
                    job.job_id, status="expired", export_uri=None, export_checksum=None
                )
                self.items = {
                    key: item
                    for key, item in self.items.items()
                    if key[0] != job.job_id
                }
                expired.append(job.job_id)
        return expired

    def _replace_job(self, job_id: UUID, **changes: Any) -> None:
        job = self.jobs[job_id]
        values = {name: getattr(job, name) for name in job.__dataclass_fields__}
        values.update(changes)
        values["updated_at"] = utc_now()
        self.jobs[job_id] = BulkJobRecord(**values)


def _replace_item(item: BulkItemRecord, **changes: Any) -> BulkItemRecord:
    values = {name: getattr(item, name) for name in item.__dataclass_fields__}
    values.update(changes)
    return BulkItemRecord(**values)


def _job(row: Mapping[str, Any]) -> BulkJobRecord:
    request = row["request"]
    warnings = row["warnings"]
    return BulkJobRecord(
        job_id=row["job_id"],
        job_kind=row["job_kind"],
        idempotency_key=row["idempotency_key"],
        request=dict(request) if not isinstance(request, str) else json.loads(request),
        status=row["status"],
        cursor=row["cursor"],
        producer_done=row["producer_done"],
        selection_truncated=row["selection_truncated"],
        next_cursor=row["next_cursor"],
        warnings=tuple(
            warnings if not isinstance(warnings, str) else json.loads(warnings)
        ),
        cancel_requested=row["cancel_requested"],
        export_uri=row["export_uri"],
        export_checksum=row["export_checksum"],
        finalizer_owner=row["finalizer_owner"],
        finalizer_lease_expires_at=row["finalizer_lease_expires_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
    )


def _item(row: Mapping[str, Any]) -> BulkItemRecord:
    return BulkItemRecord(
        job_id=row["job_id"],
        item_key=row["item_key"],
        payload_uri=row["payload_uri"],
        payload_checksum=row["payload_checksum"],
        status=row["status"],
        attempt_count=row["attempt_count"],
        lease_owner=row["lease_owner"],
        lease_expires_at=row["lease_expires_at"],
        output_uri=row["output_uri"],
        output_checksum=row["output_checksum"],
        generation_mode=row["generation_mode"],
        error_code=row["error_code"],
    )
