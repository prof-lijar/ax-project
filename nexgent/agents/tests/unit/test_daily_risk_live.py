"""Live copies must commit before the scheduler reports success."""

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
@pytest.mark.parametrize("apply", [True, False])
@pytest.mark.parametrize("target", ["local", "dev", "prod", "both"])
async def test_live_commit_precedes_success(monkeypatch, capsys, apply, target):
    connection, transaction = connection_fixture()
    stages = []
    transaction.__aexit__.side_effect = lambda *args: stages.append("local_commit")
    monkeypatch.setattr(run, "database_dsn", lambda: "private")
    monkeypatch.setattr(run, "sync_target", lambda: target)
    monkeypatch.setattr(run.asyncpg, "connect", AsyncMock(return_value=connection))
    destinations = {
        "local": [],
        "dev": ["dev"],
        "prod": ["prod"],
        "both": ["dev", "prod"],
    }
    expected = destinations[target] if apply else []

    async def copy(source, month, *, target_name, **kwargs):
        assert source is connection
        assert month == "2026.01"
        index = expected.index(target_name)
        assert stages == ["local_commit", *expected[:index]]
        stages.append(target_name)
        return {"target": target_name, "mode": "committed", "written": 2}

    sync = AsyncMock(side_effect=copy)
    monkeypatch.setattr(run, "sync_month", sync)

    async def notify(*args, **kwargs):
        assert "issue" not in kwargs
        assert stages == ["local_commit", *expected]

    sender = AsyncMock(side_effect=notify)
    monkeypatch.setattr(run, "notify_status", sender)
    await run.run(DAY, apply=apply)
    assert sync.await_count == len(expected)
    assert sender.await_count == int(apply)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    completed = events[-1]
    assert completed["event"] == "daily_risk_completed"
    assert list(completed.get("live_targets", {})) == expected
    if "dev" in expected:
        assert completed["live"] == completed["live_targets"]["dev"]
    assert [
        e["target"] for e in events if e["event"] == "daily_risk_live_completed"
    ] == expected


@pytest.mark.parametrize("failed_target", ["dev", "prod"])
def test_live_failure_cannot_report_success_and_replay_recovers(
    monkeypatch, capsys, failed_target
):
    connection, _ = connection_fixture()
    monkeypatch.setattr(run, "database_dsn", lambda: "private")
    monkeypatch.setattr(run, "sync_target", lambda: "both")
    monkeypatch.setattr(run.asyncpg, "connect", AsyncMock(return_value=connection))

    async def copy(*args, target_name, **kwargs):
        if target_name == failed_target:
            raise RuntimeError("SECRET")
        return {"target": target_name, "mode": "committed"}

    sync = AsyncMock(side_effect=copy)
    monkeypatch.setattr(run, "sync_month", sync)
    sender = AsyncMock()
    monkeypatch.setattr(run, "notify_status", sender)
    assert run.main(["--date", DAY.isoformat(), "--apply"]) == 1
    assert f"Live {failed_target} copy" in sender.call_args.kwargs["issue"]
    assert "local archive already committed" in sender.call_args.kwargs["issue"]
    output = capsys.readouterr().out
    assert "SECRET" not in output
    assert '"event": "daily_risk_completed"' not in output
    events = [json.loads(line) for line in output.splitlines()]
    assert events[-1]["event"] == "daily_risk_failed"
    assert f"Live {failed_target} copy" in events[-1]["stage"]
    assert [
        e["target"] for e in events if e["event"] == "daily_risk_live_completed"
    ] == (["dev"] if failed_target == "prod" else [])
    assert [c.kwargs["target_name"] for c in sync.await_args_list] == (
        ["dev", "prod"] if failed_target == "prod" else ["dev"]
    )
    connection.close.assert_awaited_once()

    # Replaying the same date retries both destinations after reconciliation.
    sync.reset_mock(side_effect=True)
    sync.return_value = {"mode": "committed", "written": 0}
    sender.reset_mock()
    assert run.main(["--date", DAY.isoformat(), "--apply"]) == 0
    assert [c.kwargs["target_name"] for c in sync.await_args_list] == ["dev", "prod"]
    assert "issue" not in sender.call_args.kwargs


@pytest.mark.asyncio
async def test_local_failure_prevents_all_live_writes(monkeypatch):
    connection, transaction = connection_fixture()
    transaction.__aexit__.side_effect = RuntimeError("commit failed")
    monkeypatch.setattr(run, "database_dsn", lambda: "private")
    monkeypatch.setattr(run, "sync_target", lambda: "both")
    monkeypatch.setattr(run.asyncpg, "connect", AsyncMock(return_value=connection))
    sync = AsyncMock()
    monkeypatch.setattr(run, "sync_month", sync)
    monkeypatch.setattr(run, "notify_status", AsyncMock())
    with pytest.raises(RuntimeError):
        await run.run(DAY, apply=True)
    sync.assert_not_awaited()


def test_production_explicitly_targets_both_live_databases():
    manifest = yaml.safe_load((run.ROOT.parent / "compose.prod.yaml").read_text())
    service = manifest["services"]["daily-risk-scheduler"]
    assert service["environment"]["DAILY_RISK_SYNC_TARGET"] == "both"


@pytest.mark.parametrize("target", ["local", "dev", "prod", "both"])
def test_target_configuration_and_process_override(tmp_path, monkeypatch, target):
    monkeypatch.setattr(run, "ROOT", tmp_path)
    (tmp_path / ".env").write_text(f"DAILY_RISK_SYNC_TARGET={target}\n")
    monkeypatch.delenv("DAILY_RISK_SYNC_TARGET", raising=False)
    assert run.sync_target() == target
    monkeypatch.setenv("DAILY_RISK_SYNC_TARGET", "local")
    assert run.sync_target() == "local"


def test_local_default_and_invalid_target(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.delenv("DAILY_RISK_SYNC_TARGET", raising=False)
    assert run.sync_target() == "local"
    monkeypatch.setenv("DAILY_RISK_SYNC_TARGET", "production")
    with pytest.raises(ValueError, match="local, dev, prod or both"):
        run.sync_target()


def live_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "".join(
            f"LIVE_{name.upper()}_DB_HOST={name}.internal\n"
            f"LIVE_{name.upper()}_DB_USER={name}_user\n"
            f"LIVE_{name.upper()}_DB_PASSWORD={name}-secret\n"
            f"LIVE_{name.upper()}_SSH_HOST={name}-bastion.internal\n"
            f"LIVE_{name.upper()}_SSH_ID={name}_operator\n"
            f"LIVE_{name.upper()}_SSH_PASSWORD={name}-ssh-secret\n"
            for name in ("dev", "prod")
        )
    )
    for key in list(live.os.environ):
        if key.startswith(("LIVE_DEV_", "LIVE_PROD_")):
            monkeypatch.delenv(key)
    return env_file


@pytest.mark.asyncio
@pytest.mark.parametrize("target_name", ["dev", "prod"])
async def test_live_adapter_isolates_settings_and_copies_only_processed_month(
    tmp_path, monkeypatch, target_name
):
    env_file = live_env(tmp_path, monkeypatch)

    @asynccontextmanager
    async def tunnel(settings):
        assert settings.db_host == f"{target_name}.internal"
        assert settings.ssh_host == f"{target_name}-bastion.internal"
        assert settings.ssh_user == f"{target_name}_operator"
        yield 15432

    source, target = AsyncMock(), AsyncMock()
    source.fetchrow.return_value = ("archive", "127.0.0.1", 5432)
    target.fetchrow.return_value = ("ansimk", f"{target_name}.internal", 5432)
    connector = AsyncMock(return_value=target)
    copier = AsyncMock(return_value={"written": 2})
    monkeypatch.setattr(live, "dev_tunnel", tunnel)
    monkeypatch.setattr(live.asyncpg, "connect", connector)
    monkeypatch.setattr(live, "copy_rows", copier)
    kwargs = {
        "env_file": env_file,
        "event": lambda *a, **kw: None,
        "target_name": target_name,
    }
    assert await live.sync_month(source, "2026.10", **kwargs) == {"written": 2}
    assert connector.call_args.kwargs["user"] == f"{target_name}_user"
    assert connector.call_args.kwargs["password"] == f"{target_name}-secret"
    assert connector.call_args.kwargs["ssl"] == (
        "require" if target_name == "prod" else "prefer"
    )
    copier.assert_awaited_once_with(
        source,
        target,
        schema="ansimk",
        write=True,
        month="2026.10",
        target_name=target_name,
    )
    target.close.assert_awaited_once()

    copier.side_effect = RuntimeError("verification failed")
    with pytest.raises(RuntimeError, match="verification failed"):
        await live.sync_month(source, "2026.10", **kwargs)
    assert target.close.await_count == 2

    copier.reset_mock()
    target.fetchrow.return_value = source.fetchrow.return_value
    with pytest.raises(ValueError, match="must differ"):
        await live.sync_month(source, "2026.10", **kwargs)
    copier.assert_not_awaited()
    assert target.close.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["password", "schema"])
async def test_invalid_prod_settings_never_fall_back_to_dev(
    tmp_path, monkeypatch, problem
):
    env_file = live_env(tmp_path, monkeypatch)
    content = env_file.read_text()
    if problem == "password":
        content = content.replace("LIVE_PROD_DB_PASSWORD=prod-secret\n", "")
    else:
        content += "LIVE_PROD_DB_SCHEMA=wrong_schema\n"
    env_file.write_text(content)
    connector = AsyncMock()
    monkeypatch.setattr(live.asyncpg, "connect", connector)
    with pytest.raises(ValueError, match=f"LIVE_PROD_DB_{problem.upper()}"):
        await live.sync_month(
            AsyncMock(),
            "2026.10",
            env_file=env_file,
            event=lambda *a, **kw: None,
            target_name="prod",
        )
    connector.assert_not_awaited()
