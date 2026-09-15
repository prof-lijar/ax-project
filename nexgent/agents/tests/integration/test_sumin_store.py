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
                "SELECT count(*) FROM sumin.events WHERE status IN ('pending','running')"
            )
            == 0
        )
        try:
            await asyncio.gather(store.enqueue([work]), store.enqueue([work]))
            assert (
                await pool.fetchval(
                    "SELECT count(*) FROM sumin.events WHERE key=$1", work.key
                )
                == 1
            )
            rows = await asyncio.gather(store.claim(), Store(pool).claim())
            assert sum(row is not None for row in rows) == 1
            old = next(row for row in rows if row is not None)
            await pool.execute(
                "UPDATE sumin.events SET lease_until=NOW()-INTERVAL '1 second' WHERE key=$1",
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
                    "SELECT status FROM sumin.events WHERE key=$1", work.key
                )
                == "running"
            )
            await store.finish(reclaimed, "nextcloud_upload_failed")
            assert await store.claim() is None  # Backoff is durable.
            for attempt in (3, 4, 5):
                await pool.execute(
                    "UPDATE sumin.events SET available_at=NOW() WHERE key=$1", work.key
                )
                row = await store.claim()
                assert row["attempts"] == attempt
                await store.finish(row, "nextcloud_upload_failed")
            assert (
                await pool.fetchval(
                    "SELECT status FROM sumin.events WHERE key=$1", work.key
                )
                == "failed"
            )
            assert await store.claim() is None
            folder = await store.folder(team, work.channel_id, f"Slack/{team}/finance")
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
            await pool.execute("DELETE FROM sumin.events WHERE key=$1", work.key)
            for table in ("contexts", "files", "channels"):
                await pool.execute(f"DELETE FROM sumin.{table} WHERE team_id=$1", team)
