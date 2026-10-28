import importlib.util
import json
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

SCRIPT = Path(__file__).parents[2] / "playground/weekly-reporter/migrate.py"
spec = importlib.util.spec_from_file_location("weekly_report_migration", SCRIPT)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.mark.parametrize(
    "override, storage, expected",
    [
        ("override", "storage", "override"),
        ("", "storage", "storage"),
        ("", "", "source"),
    ],
)
def test_source_credentials_are_separate(monkeypatch, override, storage, expected):
    monkeypatch.setenv("SOURCE_DATABASE_DSN", override)
    monkeypatch.delenv("WEEKLY_REPORT_STORAGE_DATABASE_DSN", raising=False)
    monkeypatch.delenv("ANSIMK_DATABASE_DSN", raising=False)
    monkeypatch.setenv("TARGET_DB_PASSWORD", "production-only")
    monkeypatch.setattr(
        migration,
        "dotenv_values",
        lambda path: {
            "WEEKLY_REPORT_STORAGE_DATABASE_DSN": storage,
            "ANSIMK_DATABASE_DSN": "source",
        },
    )
    assert migration.source_database_dsn() == expected


@pytest.mark.asyncio
async def test_migration_loads_root_env_and_namespaced_production_credentials(monkeypatch):
    loaded = []
    monkeypatch.setattr(migration, "load_dotenv", lambda path, **kw: loaded.append(path))
    monkeypatch.setattr(migration, "source_database_dsn", lambda: "local-source")
    for key, value in {
        "LIVE_PROD_DB_USER": "production-user",
        "LIVE_PROD_DB_PASSWORD": "production-password",
        "LIVE_PROD_DB_NAME": "production-reports",
        "LIVE_PROD_DB_SSL": "require",
        "LIVE_PROD_TUNNEL_PORT": "16543",
        "LIVE_PROD_DB_HOST": "remote-db.example",
        "TARGET_DB_HOST": "obsolete-db.example",
        "TARGET_DB_USER": "obsolete-user",
    }.items():
        monkeypatch.setenv(key, value)
    source, target = AsyncMock(), AsyncMock()
    source.fetchrow.return_value = "local-identity"
    target.fetchrow.return_value = "production-identity"
    connect = AsyncMock(side_effect=[source, target])
    monkeypatch.setattr(migration.asyncpg, "connect", connect)
    transfer = AsyncMock(return_value={"source": 0})
    monkeypatch.setattr(migration, "migrate", transfer)
    await migration.run(SimpleNamespace(write=False, week_start=date(2026, 10, 19)))
    assert loaded == [SCRIPT.resolve().parents[2] / ".env"]
    assert connect.call_args.kwargs["host"] == "127.0.0.1"
    assert connect.call_args.kwargs["port"] == 16543
    assert connect.call_args.kwargs["user"] == "production-user"
    assert connect.call_args.kwargs["password"] == "production-password"
    assert connect.call_args.kwargs["database"] == "production-reports"
    source.close.assert_awaited_once()
    target.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("storage", ["local-storage", ""])
async def test_notification_coverage_uses_only_local_agent_database(
    monkeypatch, tmp_path, storage,
):
    monkeypatch.setenv("SOURCE_DATABASE_DSN", "migration-override")
    monkeypatch.setenv("TARGET_DB_USER", "production-user")
    monkeypatch.setenv("TARGET_DB_PASSWORD", "production-password")
    for key in ("WEEKLY_REPORT_STORAGE_DATABASE_DSN", "ANSIMK_DATABASE_DSN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(migration, "dotenv_values", lambda path: {
        "WEEKLY_REPORT_STORAGE_DATABASE_DSN": storage,
        "ANSIMK_DATABASE_DSN": "local-source",
    })
    load = lambda *a, **kw: pytest.fail("coverage must not load production config")
    monkeypatch.setattr(migration, "load_dotenv", load)
    connection = AsyncMock()
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr(migration.asyncpg, "connect", connect)
    from workflows.weekly_report import completion_notification as coverage
    collect = AsyncMock(return_value={"version": 2, "weeks": []})
    monkeypatch.setattr(coverage, "collect_coverage", collect)
    output = tmp_path / "coverage.json"
    args = SimpleNamespace(write=False, week_start=date(2026, 10, 19), coverage_output=output)
    await migration.run(args)
    assert connect.call_args.args == (storage or "local-source",)
    assert not {"user", "password", "host", "port"} & connect.call_args.kwargs.keys()
    collect.assert_awaited_once_with(connection, args.week_start)
    connection.close.assert_awaited_once()
    assert json.loads(output.read_text()) == {"version": 2, "weeks": []}


@pytest.mark.asyncio
async def test_notification_coverage_closes_local_connection_on_failure(monkeypatch, tmp_path):
    from workflows.weekly_report import completion_notification as coverage
    monkeypatch.setattr(migration, "local_database_dsn", lambda: "local-source")
    connection = AsyncMock()
    monkeypatch.setattr(migration.asyncpg, "connect", AsyncMock(return_value=connection))
    monkeypatch.setattr(coverage, "collect_coverage", AsyncMock(side_effect=ValueError("failed")))
    output = tmp_path / "coverage.json"
    with pytest.raises(ValueError, match="failed"):
        await migration.export_coverage(SimpleNamespace(
            write=False, week_start=date(2026, 10, 19), coverage_output=output,
        ))
    connection.close.assert_awaited_once()
    assert not output.exists()


@pytest.mark.parametrize("option", ["--coverage-output", "--coverage-output=coverage.json"])
def test_coverage_shell_bypasses_ssh_and_production_credentials(tmp_path, option):
    script = tmp_path / "migrate.sh"
    script.write_text(SCRIPT.with_suffix(".sh").read_text())
    python = tmp_path / "fake-python"
    python.write_text(f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
    python.chmod(0o700)
    args = [option] + (["coverage.json"] if option == "--coverage-output" else [])
    result = subprocess.run(
        ["bash", str(script), "--week-start", "2026-10-19", *args],
        env={"PATH": "/usr/bin:/bin", "PYTHON_BIN": str(python)},
        capture_output=True, text=True, timeout=5, check=True,
    )
    assert json.loads(result.stdout) == [
        str(tmp_path / "migrate.py"), "--week-start", "2026-10-19", *args,
    ]


class Database:
    def __init__(self, rows=(), existing=None, ward_exists=True):
        self.rows = rows
        self.existing = existing
        self.ward_exists = ward_exists
        self.writes = []
        self.rolled_back = False

    @asynccontextmanager
    async def transaction(self, **kwargs):
        self.readonly = kwargs["readonly"]
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise

    async def cursor(self, query, *args, **kwargs):
        assert "FROM archive.resources_ward_weekly_report" in query
        assert "ansimk." not in query
        for row in self.rows:
            yield row

    async def fetchval(self, *args):
        assert "FROM ansimk.resources_ward" in args[0]
        return self.ward_exists

    async def fetchrow(self, *args):
        assert "FROM ansimk.resources_ward_weekly_report" in args[0]
        return self.existing

    async def execute(self, query, *args):
        assert not self.readonly
        assert "ansimk.resources_ward_weekly_report" in query
        assert "archive." not in query
        self.writes.append((query, args))
        return "INSERT 0 1"


class Row(dict):
    # asyncpg.Record iteration produces values.
    def __iter__(self):
        return iter(self.values())


def report():
    return Row(
        ward_id=1,
        week_start_date=date(2026, 8, 31),
        week_end_date=date(2026, 9, 6),
        weekly_score=80,
        weekly_status="GOOD",
        report_data='{"a": 1, "b": 2}',
        created_at=None,
        updated_at=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("write", [False, True])
@pytest.mark.parametrize("kind", ["insert", "update", "unchanged"])
async def test_preview_and_apply(write, kind):
    row = report()
    existing = None if kind == "insert" else dict(row.items())
    if kind == "update":
        existing["weekly_score"] = 50
    elif kind == "unchanged":
        existing["report_data"] = '{"b":2,"a":1}'
    source, target = Database([row]), Database(existing=existing)
    counts = await migration.migrate(source, target, write=write)
    expected = "insert" if kind == "insert" else "update"
    assert counts["source"] == counts[expected] == 1
    assert counts["unchanged"] == 0
    assert source.readonly
    assert target.readonly == (not write)
    upserts = [args for query, args in target.writes if query == migration.UPSERT]
    assert len(upserts) == int(write)
    if upserts:
        assert upserts[0] == tuple(row)[:7]


def test_existing_creation_timestamp_is_not_overwritten():
    update_sql = migration.UPSERT.split("DO UPDATE SET", 1)[1]
    assert "created_at" not in update_sql
    assert "updated_at = NOW()" in update_sql
    assert "WHERE" not in update_sql


@pytest.mark.asyncio
@pytest.mark.parametrize("write", [False, True])
@pytest.mark.parametrize("all_missing", [False, True])
async def test_missing_wards_are_skipped(write, all_missing, capsys):
    rows = [report(), report(), report()]
    for ward_id, row in enumerate(rows, start=1):
        row["ward_id"] = ward_id

    class Target(Database):
        async def fetchval(self, query, ward_id):
            return not all_missing and ward_id == 2

    source, target = Database(rows), Target()
    counts = await migration.migrate(source, target, write=write)
    assert counts == {
        "source": 3,
        "insert": 0 if all_missing else 1,
        "update": 0,
        "unchanged": 0,
        "skipped": 3 if all_missing else 2,
    }
    assert not target.rolled_back
    assert source.readonly
    assert target.readonly == (not write)
    upserts = [args for query, args in target.writes if query == migration.UPSERT]
    assert [args[0] for args in upserts] == (
        [2] if write and not all_missing else []
    )
    output = capsys.readouterr().out
    for ward_id in ([1, 2, 3] if all_missing else [1, 3]):
        assert f"ward_id={ward_id}, week_start_date=2026-08-31" in output
    assert output.count("Skipping report:") == counts["skipped"]


@pytest.mark.asyncio
async def test_write_failure_after_skip_still_aborts_transaction():
    rows = [report(), report()]
    rows[1]["ward_id"] = 2

    class Target(Database):
        async def fetchval(self, query, ward_id):
            return ward_id == 2

        async def execute(self, query, *args):
            if query == migration.UPSERT:
                raise ValueError("write failed")
            return await super().execute(query, *args)

    source, target = Database(rows), Target()
    with pytest.raises(ValueError, match="write failed"):
        await migration.migrate(source, target, write=True)
    assert target.rolled_back
