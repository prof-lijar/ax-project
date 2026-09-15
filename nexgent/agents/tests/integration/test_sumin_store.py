"""Opt-in PostgreSQL test. SUMIN_TEST_DATABASE_DSN must name a disposable test database."""

import asyncio
import os
import uuid
from pathlib import Path

import asyncpg
import pytest
from ax_contracts.sumin import SuminTask

from workflows.sumin.store import Store


@pytest.mark.asyncio
async def test_postgres_dedup_claim_restart_fencing_and_terminal_retry():
    dsn = os.environ.get("SUMIN_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("SUMIN_TEST_DATABASE_DSN is not configured")
    team = "T" + uuid.uuid4().hex.upper()
    work = SuminTask(
        event_id="Ev" + uuid.uuid4().hex,
        team_id=team,
        channel_id="C12345678",
        kind="archive",
        file_id="F12345678",
        text="Quarterly budget",
    )
    async with asyncpg.create_pool(
        dsn, min_size=2, max_size=4, command_timeout=10
    ) as pool:
        database = await pool.fetchval("SELECT current_database()")
        if "test" not in database.lower():
            pytest.fail(
                "Sumin integration test requires a database name containing 'test'"
            )
        await pool.execute(Path("workflows/sumin/schema.sql").read_text())
        store = Store(pool)
        # A test database must not contain runnable jobs from another test/operator.
        assert (
            await pool.fetchval(
                "SELECT count(*) FROM agent.sumin_events WHERE status IN ('pending','running')"
            )
            == 0
        )
        try:
            await asyncio.gather(store.enqueue([work]), store.enqueue([work]))
            assert (
                await pool.fetchval(
                    "SELECT count(*) FROM agent.sumin_events WHERE key=$1", work.key
                )
                == 1
            )
            rows = await asyncio.gather(store.claim(), Store(pool).claim())
            assert sum(row is not None for row in rows) == 1
            old = next(row for row in rows if row is not None)
            await pool.execute(
                "UPDATE agent.sumin_events SET lease_until=NOW()-INTERVAL '1 second' WHERE key=$1",
                work.key,
            )
            reclaimed = await Store(pool).claim()
            assert (
                reclaimed["attempts"] == 2
                and reclaimed["lease_token"] != old["lease_token"]
            )
            await store.finish(old)
            assert (
                await pool.fetchval(
                    "SELECT status FROM agent.sumin_events WHERE key=$1", work.key
                )
                == "running"
            )
            await store.finish(reclaimed, "nextcloud_upload_failed")
            assert await store.claim() is None  # Backoff is durable.
            for attempt in (3, 4, 5):
                await pool.execute(
                    "UPDATE agent.sumin_events SET available_at=NOW() WHERE key=$1",
                    work.key,
                )
                row = await store.claim()
                assert row["attempts"] == attempt
                await store.finish(row, "nextcloud_upload_failed")
            assert (
                await pool.fetchval(
                    "SELECT status FROM agent.sumin_events WHERE key=$1", work.key
                )
                == "failed"
            )
            assert await store.claim() is None
            folder = await store.folder(team, work.channel_id, "Slack/finance")
            assert await store.folder(team, work.channel_id, "renamed") == folder
            with pytest.raises(asyncpg.UniqueViolationError):
                await store.folder(team, "COTHER123", folder)
            path = await store.file_path(work, folder + "/F12345678--plan.pdf")
            assert await store.file_path(work, folder + "/new-name.pdf") == path
            await store.save_context(work)
            await store.save_context(work)
            assert await store.match_context(work, ["budget"]) == {work.file_id}
            other = work.model_copy(update={"channel_id": "COTHER123"})
            assert await store.match_context(other, ["budget"]) == set()
        finally:
            await pool.execute("DELETE FROM agent.sumin_events WHERE key=$1", work.key)
            for table in ("contexts", "files", "channels"):
                await pool.execute(
                    f"DELETE FROM agent.sumin_{table} WHERE team_id=$1", team
                )


@pytest.mark.asyncio
@pytest.mark.parametrize("archive_root", ["Slack", "Shared/Slack"])
async def test_channel_folder_migration_preserves_paths_and_runs_once(archive_root):
    dsn = os.environ.get("SUMIN_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("SUMIN_TEST_DATABASE_DSN is not configured")
    connection = await asyncpg.connect(dsn)
    try:
        if (
            "test"
            not in (await connection.fetchval("SELECT current_database()")).lower()
        ):
            pytest.fail("Sumin integration test requires a disposable test database")
        schema = Path("workflows/sumin/schema.sql").read_text()
        await connection.execute(schema)
        transaction = connection.transaction()
        await transaction.start()
        try:
            await connection.execute(
                "DELETE FROM agent.sumin_migrations WHERE name='channel-folders-v2'"
            )
            team = "T" + uuid.uuid4().hex.upper()
            root = archive_root + "/" + uuid.uuid4().hex
            old_folder = f"{root}/{team}/original-name"
            new_folder = f"{root}/original-name"
            await connection.execute(
                "INSERT INTO agent.sumin_channels VALUES($1,$2,$3)",
                team,
                "C12345678",
                old_folder,
            )
            await connection.execute(
                "INSERT INTO agent.sumin_files VALUES($1,$2,$3,$4)",
                team,
                "C12345678",
                "F12345678",
                old_folder + "/F12345678--notes.md",
            )
            await connection.execute(schema)
            assert (
                await connection.fetchval(
                    "SELECT folder FROM agent.sumin_channels WHERE team_id=$1", team
                )
                == new_folder
            )
            assert (
                await connection.fetchval(
                    "SELECT path FROM agent.sumin_files WHERE team_id=$1", team
                )
                == new_folder + "/F12345678--notes.md"
            )
            # A fresh custom root may legitimately contain a workspace ID.
            await connection.execute(
                "INSERT INTO agent.sumin_channels VALUES($1,$2,$3)",
                team,
                "COTHER123",
                old_folder,
            )
            await connection.execute(schema)
            assert (
                await connection.fetchval(
                    "SELECT folder FROM agent.sumin_channels WHERE team_id=$1 AND channel_id=$2",
                    team,
                    "COTHER123",
                )
                == old_folder
            )
        finally:
            await transaction.rollback()
    finally:
        await connection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", [False, True])
async def test_shared_schema_migration_preserves_records_and_rejects_conflicts(
    conflict,
):
    dsn = os.environ.get("SUMIN_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("SUMIN_TEST_DATABASE_DSN is not configured")
    connection = await asyncpg.connect(dsn)
    try:
        if (
            "test"
            not in (await connection.fetchval("SELECT current_database()")).lower()
        ):
            pytest.fail("Sumin integration test requires a disposable test database")
        schema = Path("workflows/sumin/schema.sql").read_text()
        await connection.execute(schema)
        transaction = connection.transaction()
        await transaction.start()
        try:
            await connection.execute("CREATE SCHEMA IF NOT EXISTS sumin")
            tables = ("events", "channels", "files", "contexts", "migrations")
            for table in tables:
                assert (
                    await connection.fetchval(
                        "SELECT to_regclass($1)", "sumin." + table
                    )
                    is None
                )
                await connection.execute(
                    f"ALTER TABLE agent.sumin_{table} SET SCHEMA sumin"
                )
                await connection.execute(
                    f"ALTER TABLE sumin.sumin_{table} RENAME TO {table}"
                )
            # Exercise original unprefixed primary-key index names.
            await connection.execute(
                "ALTER INDEX sumin.sumin_events_pkey RENAME TO events_pkey"
            )
            await connection.execute("CREATE TABLE agent.schema_test_other (id int)")
            await connection.execute(
                "CREATE UNIQUE INDEX events_pkey ON agent.schema_test_other(id)"
            )
            key = "migration-" + uuid.uuid4().hex
            await connection.execute(
                "INSERT INTO sumin.events(key,payload,status,attempts) VALUES($1,'{}','failed',5)",
                key,
            )
            team = "T" + uuid.uuid4().hex.upper()
            folder = "Shared/Slack/" + uuid.uuid4().hex
            await connection.execute(
                "INSERT INTO sumin.channels VALUES($1,$2,$3)", team, "C12345678", folder
            )
            await connection.execute(
                "INSERT INTO sumin.files VALUES($1,$2,$3,$4)",
                team,
                "C12345678",
                "F12345678",
                folder + "/notes.md",
            )
            await connection.execute(
                "INSERT INTO sumin.contexts VALUES($1,$2,$3,$4,$5)",
                team,
                "C12345678",
                "F12345678",
                "Ev123",
                "Notes",
            )
            if conflict:
                await connection.execute(
                    "CREATE TABLE agent.sumin_files (sentinel int)"
                )
                with pytest.raises(asyncpg.RaiseError, match="migration conflict"):
                    async with connection.transaction():
                        await connection.execute(schema)
                assert (
                    await connection.fetchval(
                        "SELECT count(*) FROM sumin.events WHERE key=$1", key
                    )
                    == 1
                )
                assert (
                    await connection.fetchval(
                        "SELECT to_regclass('agent.sumin_events')"
                    )
                    is None
                )
            else:
                await connection.execute(schema)
                await connection.execute(schema)
                row = await connection.fetchrow(
                    "SELECT status,attempts FROM agent.sumin_events WHERE key=$1", key
                )
                assert dict(row) == {"status": "failed", "attempts": 5}
                assert (
                    await connection.fetchval(
                        "SELECT path FROM agent.sumin_files WHERE team_id=$1", team
                    )
                    == folder + "/notes.md"
                )
                assert (
                    await connection.fetchval(
                        "SELECT message_text FROM agent.sumin_contexts WHERE team_id=$1",
                        team,
                    )
                    == "Notes"
                )
                for table in tables:
                    assert (
                        await connection.fetchval(
                            "SELECT to_regclass($1)", "sumin." + table
                        )
                        is None
                    )
                assert (
                    await connection.fetchval(
                        "SELECT to_regclass('agent.schema_test_other')"
                    )
                    is not None
                )
        finally:
            await transaction.rollback()
    finally:
        await connection.close()
