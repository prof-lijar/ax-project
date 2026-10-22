"""Opt-in PostgreSQL tests with synthetic data; business tables are never written."""

import json
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import migrate_weekly_risk_counts as migration

FIXTURES = """
WITH fixture_wards AS (
    SELECT unnest($5::bigint[]) AS id
),
fixture_evaluations AS (
    SELECT * FROM unnest($6::bigint[], $7::timestamptz[], $8::text[])
        AS e(ward_id, evaluated_at, risk_level)
),
"""
TARGET_FIXTURE = """
fixture_target AS (
    SELECT * FROM jsonb_to_recordset($9::jsonb) AS t(
        id bigint, ward_id bigint, month text,
        total_risk_count int, risk_days integer[],
        total_danger_stable_count int, danger_stable_days integer[]
    )
),
"""


def fixture_query(sql, target=None, preview=False):
    query = sql.strip().removeprefix("WITH ")
    if target:
        query = query.replace("archive.resources_ward_monthly_risk_count", target)
    query = query.replace("archive.analysis_wardevaluation", "fixture_evaluations")
    query = query.replace("archive.resources_ward", "fixture_wards")
    return FIXTURES + (TARGET_FIXTURE if preview else "") + query


QUERY = fixture_query(migration.COUNTS_SQL) + " SELECT * FROM expected ORDER BY ward_id"
PREVIEW_QUERY = fixture_query(migration.PREVIEW_SQL, "fixture_target", preview=True)


@unittest.skipUnless(
    os.environ.get("RUN_MIGRATION_SQL_TESTS") == "1",
    "Set RUN_MIGRATION_SQL_TESTS=1 for PostgreSQL fixture tests.",
)
class DailyCountsSQLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncpg

        migration.load_dotenv(migration.ENV_FILE, override=False)
        self.connection = await asyncpg.connect(
            migration.source_database_dsn(), timeout=15, command_timeout=30
        )
        self.local = ZoneInfo("Asia/Seoul")

    async def asyncTearDown(self):
        await self.connection.close()

    def params(self, month, wards, evaluations):
        return (
            *migration.month_bounds(month, self.local),
            self.local.key,
            f"{month:%Y.%m}",
            wards,
            [e[0] for e in evaluations],
            [e[1] for e in evaluations],
            [e[2] for e in evaluations],
        )

    def event(self, ward, day, hour, risk, minute=0):
        return ward, datetime(2026, 10, day, hour, minute, tzinfo=self.local), risk

    async def counts(self, wards, evaluations, month=date(2026, 10, 1)):
        async with self.connection.transaction(readonly=True):
            rows = await self.connection.fetch(
                QUERY, *self.params(month, wards, evaluations)
            )
        result = {}
        for row in rows:
            danger, recovered = row["risk_days"], row["danger_stable_days"]
            self.assertEqual(danger, sorted(set(danger)))
            self.assertEqual(recovered, sorted(set(recovered)))
            self.assertEqual(row["total_risk_count"], len(danger))
            self.assertEqual(row["total_danger_stable_count"], len(recovered))
            self.assertTrue(set(recovered).issubset(danger))
            result[row["ward_id"]] = (danger, recovered)
        return result

    async def test_recovery_order_intermediate_states_and_daily_deduplication(self):
        events = [
            self.event(1, 14, 8, "DANGER"),
            self.event(1, 14, 9, "STABLE"),
            self.event(1, 14, 10, "DANGER"),
            self.event(1, 14, 11, "STABLE"),
            self.event(2, 14, 8, "STABLE"),
            self.event(2, 14, 9, "DANGER"),
            self.event(2, 14, 10, "CAUTION"),
            self.event(2, 14, 11, "STABLE"),
            self.event(3, 14, 8, "STABLE"),
            self.event(3, 14, 9, "DANGER"),
            self.event(4, 14, 8, "DANGER"),
            self.event(4, 14, 9, "CAUTION"),
            self.event(5, 14, 8, "CAUTION"),
            self.event(5, 14, 9, "STABLE"),
            self.event(6, 14, 8, "DANGER"),
            self.event(6, 14, 8, "STABLE"),
            self.event(7, 14, 8, "DANGER"),
            self.event(7, 14, 9, "STABLE"),
            self.event(7, 14, 10, "DANGER"),
        ]
        self.assertEqual(
            await self.counts(list(range(1, 9)), events),
            {
                1: ([14], [14]),
                2: ([14], [14]),
                3: ([14], []),
                4: ([14], []),
                5: ([], []),
                6: ([14], []),
                7: ([14], [14]),
                8: ([], []),
            },
        )

    async def test_timezone_midnight_and_month_boundaries(self):
        events = [
            (1, datetime(2026, 10, 13, 14, 59, tzinfo=timezone.utc), "DANGER"),
            (1, datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc), "STABLE"),
            (1, datetime(2026, 10, 14, 14, 58, tzinfo=timezone.utc), "DANGER"),
            (1, datetime(2026, 10, 14, 14, 59, tzinfo=timezone.utc), "STABLE"),
            (1, datetime(2026, 9, 30, 14, 59, tzinfo=timezone.utc), "DANGER"),
            (1, datetime(2026, 10, 31, 14, 59, tzinfo=timezone.utc), "DANGER"),
            (1, datetime(2026, 10, 31, 15, 0, tzinfo=timezone.utc), "STABLE"),
        ]
        self.assertEqual(await self.counts([1], events), {1: ([13, 14, 31], [14])})

    async def test_sorted_arrays_known_recovery_example_and_no_cross_ward_pair(self):
        events = [
            self.event(1, 20, 8, "DANGER"),
            self.event(1, 20, 9, "STABLE"),
            self.event(1, 3, 8, "DANGER"),
            self.event(1, 14, 8, "DANGER"),
            self.event(1, 14, 9, "STABLE"),
            self.event(2, 3, 9, "STABLE"),
            self.event(13013, 5, 8, "DANGER", 18),
            self.event(13013, 5, 8, "STABLE", 23),
        ]
        self.assertEqual(
            await self.counts([1, 2, 13013], events),
            {
                1: ([3, 14, 20], [14, 20]),
                2: ([], []),
                13013: ([5], [5]),
            },
        )

    async def test_many_evaluations_count_once_and_empty_source_is_zero(self):
        events = [
            (
                1,
                datetime(2026, 10, day, 8, tzinfo=self.local) + timedelta(seconds=i),
                "DANGER",
            )
            for day in range(1, 32)
            for i in range(100)
        ]
        events += [self.event(1, day, 9, "STABLE") for day in range(1, 32)]
        self.assertEqual(
            await self.counts([1, 2], events),
            {
                1: (list(range(1, 32)), list(range(1, 32))),
                2: ([], []),
            },
        )
        self.assertEqual(await self.counts([1], []), {1: ([], [])})

    async def test_leap_day(self):
        events = [
            (1, datetime(2024, 2, 29, hour, tzinfo=self.local), risk)
            for hour, risk in ((8, "DANGER"), (9, "STABLE"))
        ]
        self.assertEqual(
            await self.counts([1], events, date(2024, 2, 1)),
            {
                1: ([29], [29]),
            },
        )

    async def test_preview_detects_null_stale_and_recovery_only_changes(self):
        events = [self.event(1, 14, 8, "DANGER"), self.event(1, 14, 9, "STABLE")]
        good = {
            "id": 1,
            "ward_id": 1,
            "month": "2026.10",
            "total_risk_count": 1,
            "risk_days": [14],
            "total_danger_stable_count": 1,
            "danger_stable_days": [14],
        }
        for change, updates in (
            ({}, 0),
            ({"danger_stable_days": None}, 1),
            ({"total_danger_stable_count": 0}, 1),
            ({"danger_stable_days": [13]}, 1),
            ({"danger_stable_days": [14, 14]}, 1),
            ({"risk_days": None}, 1),
        ):
            with self.subTest(change=change):
                async with self.connection.transaction(readonly=True):
                    row = await self.connection.fetchrow(
                        PREVIEW_QUERY,
                        *self.params(date(2026, 10, 1), [1, 2], events),
                        json.dumps([{**good, **change}]),
                    )
                self.assertEqual(row["updates"], updates)
                self.assertEqual(row["inserts"], 1)
                self.assertEqual(row["danger_days"], 1)
                self.assertEqual(row["danger_stable_days"], 1)
        stale = {
            **good,
            "total_risk_count": 0,
            "risk_days": [],
            "total_danger_stable_count": 0,
            "danger_stable_days": [14],
        }
        async with self.connection.transaction(readonly=True):
            row = await self.connection.fetchrow(
                PREVIEW_QUERY,
                *self.params(date(2026, 10, 1), [1], []),
                json.dumps([stale]),
            )
        self.assertEqual(row["updates"], 1)
        self.assertEqual(row["danger_stable_days"], 0)

    async def test_upsert_to_temporary_table_is_idempotent_and_preserves_identity(self):
        transaction = self.connection.transaction()
        await transaction.start()
        try:
            await self.connection.execute("""
                CREATE TEMP TABLE risk_migration_fixture (
                    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    ward_id bigint NOT NULL, month varchar(7) NOT NULL,
                    total_risk_count integer NOT NULL DEFAULT 0, risk_days integer[],
                    total_danger_stable_count integer NOT NULL DEFAULT 0,
                    danger_stable_days integer[],
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(ward_id, month)
                )
            """)
            query = fixture_query(
                migration.UPSERT_SQL, "pg_temp.risk_migration_fixture"
            )
            events = [self.event(1, 14, 8, "DANGER"), self.event(1, 14, 9, "STABLE")]
            params = self.params(date(2026, 10, 1), [1, 2], events)
            self.assertEqual(await self.connection.fetchval(query, *params), 2)
            original = await self.connection.fetchrow(
                "SELECT * FROM pg_temp.risk_migration_fixture WHERE ward_id=1"
            )
            self.assertEqual(original["danger_stable_days"], [14])
            self.assertEqual(original["total_danger_stable_count"], 1)
            self.assertEqual(await self.connection.fetchval(query, *params), 0)
            await self.connection.execute("""
                UPDATE pg_temp.risk_migration_fixture
                SET danger_stable_days=ARRAY[13] WHERE ward_id=1
            """)
            self.assertEqual(await self.connection.fetchval(query, *params), 1)
            fixed = await self.connection.fetchrow(
                "SELECT * FROM pg_temp.risk_migration_fixture WHERE ward_id=1"
            )
            self.assertEqual(fixed["danger_stable_days"], [14])
            self.assertEqual(fixed["id"], original["id"])
            self.assertEqual(fixed["created_at"], original["created_at"])
            zero = await self.connection.fetchrow(
                "SELECT * FROM pg_temp.risk_migration_fixture WHERE ward_id=2"
            )
            self.assertEqual(zero["risk_days"], [])
            self.assertEqual(zero["danger_stable_days"], [])
        finally:
            await transaction.rollback()


if __name__ == "__main__":
    unittest.main()
