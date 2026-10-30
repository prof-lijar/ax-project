"""Live copy is required before production can report a successful run."""

import json
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock

import pytest
import yaml

from apps.daily_risk_scheduler import live, run
from tests.unit.test_daily_risk_counts import connection_fixture

DAY = date(2026, 1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "apply,target", [(True, "dev"), (False, "dev"), (True, "local")]
)
async def test_live_commit_precedes_success(monkeypatch, apply, target):
    connection, transaction = connection_fixture()
    stages = []
    transaction.__aexit__.side_effect = lambda *args: stages.append("local_commit")
    monkeypatch.setattr(run, "database_dsn", lambda: "private")
    monkeypatch.setattr(run, "sync_target", lambda: target)
    monkeypatch.setattr(run.asyncpg, "connect", AsyncMock(return_value=connection))

    async def copy(source, month, **kwargs):
        assert source is connection
        assert month == "2026.01"
        assert stages == ["local_commit"]
        stages.append("live_commit")
        return {"mode": "committed", "written": 2}

    sync = AsyncMock(side_effect=copy)
    monkeypatch.setattr(run, "sync_month", sync)

    async def notify(*args, **kwargs):
        assert "issue" not in kwargs
        assert stages == (
            ["local_commit", "live_commit"] if target == "dev" else ["local_commit"]
        )

    sender = AsyncMock(side_effect=notify)
    monkeypatch.setattr(run, "notify_status", sender)
    await run.run(DAY, apply=apply)
    assert sync.await_count == int(apply and target == "dev")
    assert sender.await_count == int(apply)


def test_live_failure_cannot_report_success(monkeypatch, capsys):
    connection, _ = connection_fixture()
    monkeypatch.setattr(run, "database_dsn", lambda: "private")
    monkeypatch.setattr(run, "sync_target", lambda: "dev")
    monkeypatch.setattr(run.asyncpg, "connect", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        run, "sync_month", AsyncMock(side_effect=RuntimeError("SECRET"))
    )
    sender = AsyncMock()
    monkeypatch.setattr(run, "notify_status", sender)
    assert run.main(["--date", DAY.isoformat(), "--apply"]) == 1
    assert "Live dev copy" in sender.call_args.kwargs["issue"]
    assert "local archive already committed" in sender.call_args.kwargs["issue"]
    output = capsys.readouterr().out
    assert "SECRET" not in output
    assert "daily_risk_completed" not in output
    assert json.loads(output.splitlines()[-1])["event"] == "daily_risk_failed"
    connection.close.assert_awaited_once()


def test_production_explicitly_targets_live_dev():
    manifest = yaml.safe_load((run.ROOT.parent / "compose.prod.yaml").read_text())
    service = manifest["services"]["daily-risk-scheduler"]
    assert service["environment"]["DAILY_RISK_SYNC_TARGET"] == "dev"


def test_invalid_target_rejected(monkeypatch):
    monkeypatch.setenv("DAILY_RISK_SYNC_TARGET", "prod")
    with pytest.raises(ValueError, match="local or dev"):
        run.sync_target()


@pytest.mark.asyncio
async def test_live_adapter_uses_dev_settings_and_ansimk_schema(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LIVE_DEV_DB_HOST=dev.internal\nLIVE_DEV_DB_USER=dev_user\n"
        "LIVE_DEV_DB_PASSWORD=secret\nLIVE_DEV_SSH_HOST=bastion.internal\n"
        "LIVE_DEV_SSH_ID=operator\nLIVE_DEV_SSH_PASSWORD=ssh-secret\n"
        "LIVE_DEV_DB_SCHEMA=ansimk\nLIVE_PROD_DB_USER=wrong_user\n"
    )
    for key in list(live.os.environ):
        if key.startswith("LIVE_DEV_"):
            monkeypatch.delenv(key)

    @asynccontextmanager
    async def tunnel(settings):
        assert settings.db_host == "dev.internal"
        yield 15432

    source, target = AsyncMock(), AsyncMock()
    source.fetchrow.return_value = ("archive", "127.0.0.1", 5432)
    target.fetchrow.return_value = ("ansimk", "dev.internal", 5432)
    connector = AsyncMock(return_value=target)
    copier = AsyncMock(return_value={"written": 2})
    monkeypatch.setattr(live, "dev_tunnel", tunnel)
    monkeypatch.setattr(live.asyncpg, "connect", connector)
    monkeypatch.setattr(live, "copy_rows", copier)
    assert await live.sync_month(
        source, "2026.10", env_file=env_file, event=lambda *a, **kw: None
    ) == {"written": 2}
    assert connector.call_args.kwargs["user"] == "dev_user"
    copier.assert_awaited_once_with(
        source, target, schema="ansimk", write=True, month="2026.10"
    )
    target.close.assert_awaited_once()

    # A failed destination verification propagates after closing the connection.
    copier.side_effect = RuntimeError("verification failed")
    with pytest.raises(RuntimeError, match="verification failed"):
        await live.sync_month(
            source, "2026.10", env_file=env_file, event=lambda *a, **kw: None
        )
    assert target.close.await_count == 2
