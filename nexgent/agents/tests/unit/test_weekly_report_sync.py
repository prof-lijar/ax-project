"""Delivery failure handling without external databases or model calls."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from workflows.weekly_report.bulk.report_store import (
    WeeklyReportStorageConfigurationError,
    WeeklyReportStorageSettings,
)
from workflows.weekly_report.sync import delivery
from workflows.weekly_report.sync.outbox import encode_payload
from workflows.weekly_report.sync.settings import SyncSettings


def production_env():
    return {
        "WEEKLY_REPORT_DEPLOYMENT": "production",
        "WEEKLY_REPORT_SYNC_ENABLED": "true",
        "WEEKLY_REPORT_SYNC_WARD_IDS_VERIFIED": "true",
        "WEEKLY_REPORT_SYNC_LOCAL_DSN": "postgresql://local/ansimk",
        "WEEKLY_REPORT_SYNC_TARGET_DSN": "postgresql://target/ansimk?sslmode=verify-full&sslrootcert=/ca.pem",
    }


@pytest.mark.parametrize(
    "key",
    [
        "WEEKLY_REPORT_DEPLOYMENT",
        "WEEKLY_REPORT_SYNC_ENABLED",
        "WEEKLY_REPORT_SYNC_WARD_IDS_VERIFIED",
        "WEEKLY_REPORT_SYNC_LOCAL_DSN",
        "WEEKLY_REPORT_SYNC_TARGET_DSN",
    ],
)
def test_sync_fails_closed_without_explicit_configuration(key):
    env = production_env()
    del env[key]
    with pytest.raises(ValueError):
        SyncSettings.from_env(env)


def test_sync_settings_hide_secrets_and_reject_same_dsn():
    env = production_env()
    assert "postgresql" not in repr(SyncSettings.from_env(env))
    env["WEEKLY_REPORT_SYNC_TARGET_DSN"] = env["WEEKLY_REPORT_SYNC_LOCAL_DSN"]
    with pytest.raises(ValueError):
        SyncSettings.from_env(env)


def test_only_explicit_production_writer_enqueues():
    env = {"ANSIMK_DATABASE_DSN": "postgresql://local/db"}
    assert not WeeklyReportStorageSettings.from_env(env).enqueue_sync
    env["WEEKLY_REPORT_SYNC_ENQUEUE"] = "true"
    with pytest.raises(WeeklyReportStorageConfigurationError):
        WeeklyReportStorageSettings.from_env(env)
    env["WEEKLY_REPORT_DEPLOYMENT"] = "production"
    assert WeeklyReportStorageSettings.from_env(env).enqueue_sync


def test_canonical_payload_deduplicates_json_key_order():
    row = (101, "2026-08-03", "2026-08-09", 90, "GOOD", '{"b":2,"a":1}')
    changed_order = (*row[:-1], '{"a":1,"b":2}')
    assert encode_payload(row) == encode_payload(changed_order)
    with pytest.raises(delivery.DeliveryError, match="invalid_payload"):
        delivery.decode_payload(
            {"payload": encode_payload(row)[0], "payload_sha256": "bad"}
        )


@pytest.mark.parametrize(
    "error,code,retryable",
    [
        (OSError("SECRET"), "connection_unavailable", True),
        (TimeoutError("SECRET"), "connection_unavailable", True),
        (asyncpg.SerializationError("SECRET"), "database_transient", True),
        (asyncpg.ForeignKeyViolationError("SECRET"), "missing_ward", False),
        (asyncpg.InsufficientPrivilegeError("SECRET"), "database_rejected", False),
        (delivery.DeliveryError("content_conflict"), "content_conflict", False),
    ],
)
@pytest.mark.asyncio
async def test_worker_classifies_failures_without_leaking_or_acknowledging(
    monkeypatch, error, code, retryable
):
    row = {"id": 1, "lease_token": uuid4()}
    outbox = AsyncMock()
    outbox.claim.return_value = row
    monkeypatch.setattr(delivery, "decode_payload", lambda row: object())
    monkeypatch.setattr(delivery, "deliver", AsyncMock(side_effect=error))
    result = await delivery.process_one(outbox, object())
    assert result == {"delivery_id": 1, "error_code": code, "retryable": retryable}
    outbox.finish.assert_awaited_once_with(
        1, row["lease_token"], error_code=code, retryable=retryable
    )


@pytest.mark.asyncio
async def test_ack_failure_keeps_delivery_reclaimable(monkeypatch):
    outbox = AsyncMock()
    outbox.claim.return_value = {"id": 1, "lease_token": uuid4()}
    outbox.finish.side_effect = OSError("local connection lost after target commit")
    monkeypatch.setattr(delivery, "decode_payload", lambda row: object())
    monkeypatch.setattr(
        delivery, "deliver", AsyncMock(return_value="inserted_or_identical")
    )
    with pytest.raises(OSError):
        await delivery.process_one(outbox, object())
    assert outbox.finish.await_count == 1


@pytest.mark.asyncio
async def test_cancellation_never_acknowledges_unfinished_work(monkeypatch):
    outbox = AsyncMock()
    outbox.claim.return_value = {"id": 1, "lease_token": uuid4()}
    monkeypatch.setattr(delivery, "decode_payload", lambda row: object())
    monkeypatch.setattr(
        delivery, "deliver", AsyncMock(side_effect=asyncio.CancelledError)
    )
    with pytest.raises(asyncio.CancelledError):
        await delivery.process_one(outbox, object())
    outbox.finish.assert_not_awaited()


@pytest.mark.parametrize(
    "suffix", ["", "?sslmode=disable", "?sslmode=require", "?sslmode=verify-full"]
)
def test_target_requires_verified_tls(suffix):
    env = production_env()
    env["WEEKLY_REPORT_SYNC_TARGET_DSN"] = "postgresql://target/db" + suffix
    with pytest.raises(ValueError, match="TLS"):
        SyncSettings.from_env(env)


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["check", "dry-run"])
async def test_readiness_failure_is_reported_even_without_pending_deliveries(
    monkeypatch, capsys, command
):
    from apps.workers import weekly_report_sync as cli

    local, target = AsyncMock(), AsyncMock()
    queue = AsyncMock()
    queue.preview.return_value = []
    monkeypatch.setattr(cli, "connect", AsyncMock(side_effect=[local, target]))
    monkeypatch.setattr(cli, "Outbox", lambda *args: queue)
    monkeypatch.setattr(cli, "check_target", AsyncMock(side_effect=OSError("SECRET")))
    result = await cli.run_command(
        cli.build_parser().parse_args([command]), SyncSettings("local", "target")
    )
    assert result == 1
    output = capsys.readouterr().out
    assert "connection_unavailable" in output
    assert "SECRET" not in output and '"ready"' not in output
    queue.preview.assert_not_awaited()
    queue.claim.assert_not_awaited()
    local.close.assert_awaited_once()
    target.close.assert_awaited_once()
