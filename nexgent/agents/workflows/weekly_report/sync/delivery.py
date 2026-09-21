"""Validate and insert reports without overwriting different production content."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date
from typing import Literal

import asyncpg
from ax_contracts import WeeklyReportTemplateData
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .outbox import Outbox, OutboxSchemaError

REPORT_TABLE = "ansimk.resources_ward_weekly_report"
WARD_TABLE = "ansimk.resources_ward"


class DeliveryError(ValueError):
    """Message is a fixed safe error code, never database diagnostics."""


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1]
    ward_id: int = Field(gt=0, strict=True)
    week_start_date: date
    week_end_date: date
    weekly_score: int | None = Field(ge=0, le=100, strict=True)
    weekly_status: str
    report_data: WeeklyReportTemplateData

    @model_validator(mode="after")
    def consistent(self) -> Payload:
        info = self.report_data.basic_info
        if (
            self.week_start_date != info.period.start_date
            or self.week_end_date != info.period.end_date
            or self.weekly_score != info.risk_score
            or self.weekly_status != info.status
            or self.week_start_date.weekday() != 0
        ):
            raise ValueError("inconsistent report metadata")
        return self

    def parameters(self) -> tuple:
        return (
            self.ward_id,
            self.week_start_date,
            self.week_end_date,
            self.weekly_score,
            self.weekly_status,
            self.report_data.model_dump_json(),
        )


def decode_payload(row) -> Payload:
    try:
        data = json.loads(row["payload"])
        canonical = json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        if hashlib.sha256(canonical.encode()).hexdigest() != row["payload_sha256"]:
            raise ValueError("checksum")
        return Payload.model_validate(data)
    except (ValueError, TypeError, KeyError):
        raise DeliveryError("invalid_payload") from None


async def inspect_target(conn: asyncpg.Connection, payload: Payload) -> str:
    # ID equivalence is a deployment prerequisite, not inferred from FK existence.
    if not await conn.fetchval(
        f"SELECT EXISTS (SELECT 1 FROM {WARD_TABLE} WHERE id=$1)", payload.ward_id
    ):
        return "skipped_missing_ward"
    matches = await conn.fetchval(
        f"SELECT week_end_date=$3 AND weekly_score IS NOT DISTINCT FROM $4 "
        "AND weekly_status IS NOT DISTINCT FROM $5 AND report_data=$6::jsonb "
        f"FROM {REPORT_TABLE} WHERE ward_id=$1 AND week_start_date=$2",
        *payload.parameters(),
    )
    if matches is False:
        raise DeliveryError("content_conflict")
    return "identical" if matches is True else "missing"


async def check_target(pool: asyncpg.Pool) -> None:
    """Check the target even when no deliveries exist. Never inserts probe rows."""
    async with pool.acquire() as conn, conn.transaction(readonly=True):
        await conn.fetch(f"SELECT id FROM {WARD_TABLE} LIMIT 0")
        await conn.fetch(
            "SELECT ward_id, week_start_date, week_end_date, weekly_score, "
            f"weekly_status, report_data, created_at, updated_at FROM {REPORT_TABLE} LIMIT 0"
        )
        unique_key = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_index i "
            "WHERE i.indrelid=$1::regclass AND i.indisunique AND i.indisvalid "
            "AND i.indimmediate AND i.indpred IS NULL AND i.indexprs IS NULL "
            "AND i.indnkeyatts=2 AND ("
            "SELECT array_agg(a.attname::text ORDER BY a.attname) "
            "FROM unnest(i.indkey) WITH ORDINALITY AS k(attnum, position) "
            "JOIN pg_catalog.pg_attribute a ON a.attrelid=i.indrelid "
            "AND a.attnum=k.attnum WHERE k.position <= i.indnkeyatts"
            ")=ARRAY['ward_id','week_start_date'])",
            REPORT_TABLE,
        )
        if not unique_key:
            raise DeliveryError("target_unique_key_missing")


async def deliver(
    pool: asyncpg.Pool, payload: Payload, *, dry_run: bool = False
) -> str:
    async with pool.acquire() as conn, conn.transaction(readonly=dry_run):
        state = await inspect_target(conn, payload)
        if dry_run or state in {"identical", "skipped_missing_ward"}:
            return state
        await conn.execute(
            f"INSERT INTO {REPORT_TABLE} (ward_id, week_start_date, week_end_date, "
            "weekly_score, weekly_status, report_data, created_at, updated_at) "
            "VALUES ($1,$2,$3,$4,$5,$6::jsonb,NOW(),NOW()) "
            "ON CONFLICT (ward_id, week_start_date) DO NOTHING",
            *payload.parameters(),
        )
        # Re-read after conflict arbitration: a concurrent insert may differ.
        if await inspect_target(conn, payload) != "identical":
            raise DeliveryError("target_verification_failed")
        return "inserted_or_identical"


def classify_error(error: Exception) -> tuple[str, bool]:
    if isinstance(error, (DeliveryError, OutboxSchemaError)):
        return str(error), False
    if isinstance(error, (OSError, TimeoutError, asyncpg.PostgresConnectionError)):
        return "connection_unavailable", True
    if isinstance(error, asyncpg.PostgresError):
        state = error.sqlstate or ""
        if state.startswith("08") or state in {
            "40001",
            "40P01",
            "57P01",
            "57P02",
            "57P03",
            "53300",
        }:
            return "database_transient", True
        return "database_rejected", False
    return "unexpected_error", False


async def process_one(outbox: Outbox, target: asyncpg.Pool) -> dict | None:
    row = await outbox.claim()
    if row is None:
        return None
    try:
        # Shorter than the lease; cancellation leaves a reclaimable delivery.
        async with asyncio.timeout(60):
            payload = decode_payload(row)
            outcome = await deliver(target, payload)
    except Exception as error:  # noqa: BLE001 -- sanitize external diagnostics
        code, retryable = classify_error(error)
        await outbox.finish(
            row["id"], row["lease_token"], error_code=code, retryable=retryable
        )
        return {"delivery_id": row["id"], "error_code": code, "retryable": retryable}
    if outcome == "skipped_missing_ward":
        await outbox.finish(row["id"], row["lease_token"], skipped=True)
        return {
            "delivery_id": row["id"],
            "outcome": outcome,
            "ward_id": payload.ward_id,
            "week_start_date": str(payload.week_start_date),
        }
    # A failed acknowledgement must never be misreported as a target failure.
    await outbox.finish(row["id"], row["lease_token"])
    return {"delivery_id": row["id"], "outcome": outcome}
