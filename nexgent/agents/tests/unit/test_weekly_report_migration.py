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
        for row in self.rows:
            yield row

    async def fetchval(self, *args):
        return self.ward_exists

    async def fetchrow(self, *args):
        return self.existing

    async def execute(self, query, *args):
        assert not self.readonly
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
async def test_missing_ward_aborts_transaction():
    source, target = Database([report()]), Database(ward_exists=False)
    with pytest.raises(ValueError, match="Target ward missing"):
        await migration.migrate(source, target, write=True)
    assert target.rolled_back
    assert not any(query == migration.UPSERT for query, _ in target.writes)
