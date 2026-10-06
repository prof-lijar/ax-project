import importlib.util
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

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
