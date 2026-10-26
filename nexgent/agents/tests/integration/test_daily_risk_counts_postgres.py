"""Synthetic temp tables only. Set DAILY_RISK_TEST_DATABASE_DSN to opt in."""

import os
from datetime import date, datetime

import asyncpg
import pytest

from workflows.daily_risk_counts import workflow


@pytest.mark.asyncio
async def test_daily_membership_boundaries_recovery_and_idempotence(monkeypatch):
    dsn = os.environ.get("DAILY_RISK_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("DAILY_RISK_TEST_DATABASE_DSN is required")
    connection = await asyncpg.connect(dsn, timeout=15)
    try:
        await connection.execute("""
            CREATE TEMP TABLE test_risk_wards (id bigint PRIMARY KEY);
            CREATE TEMP TABLE test_risk_evaluations (
                ward_id bigint, evaluated_at timestamptz, risk_level text
            );
            CREATE TEMP TABLE test_risk_counts (
                id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                ward_id bigint, month varchar(7), total_risk_count integer,
                risk_days integer[], total_danger_stable_count integer,
                danger_stable_days integer[], created_at timestamptz DEFAULT now(),
                updated_at timestamptz DEFAULT now(), UNIQUE (ward_id, month)
            );
            INSERT INTO test_risk_wards VALUES (1),(2),(3),(4),(5),(6);
            INSERT INTO test_risk_counts
                (ward_id,month,total_risk_count,risk_days,total_danger_stable_count,danger_stable_days)
            VALUES (1,'2026.01',2,ARRAY[2,31],1,ARRAY[2]),
                   (2,'2026.01',1,ARRAY[31],1,ARRAY[31]),
                   (1,'2025.12',1,ARRAY[31],0,ARRAY[]::integer[]);
        """)
        replacements = {
            "archive.resources_ward_monthly_risk_count": "test_risk_counts",
            "archive.analysis_wardevaluation": "test_risk_evaluations",
            "archive.resources_ward": "test_risk_wards",
        }
        for name in ("PREVIEW_SQL", "UPSERT_SQL", "TARGET_TABLE"):
            value = getattr(workflow, name)
            for old, new in replacements.items():
                value = value.replace(old, new)
            monkeypatch.setattr(workflow, name, value)

        def at(value):
            return datetime.fromisoformat(value).replace(tzinfo=workflow.TIMEZONE)

        rows = [
            (1, at("2026-01-31T00:00:00"), "DANGER"),
            (1, at("2026-01-31T00:01:00"), "STABLE"),
            (1, at("2026-01-31T23:59:59.999999"), "DANGER"),
            (2, at("2026-02-01T00:00:00"), "DANGER"),
            (3, at("2026-01-31T03:00:00"), "STABLE"),
            (3, at("2026-01-31T04:00:00"), "DANGER"),
            (3, at("2026-01-31T04:00:00"), "STABLE"),
            (4, at("2026-01-31T23:59:59.999999"), "DANGER"),
            (4, at("2026-02-01T00:00:00"), "STABLE"),
            (5, at("2026-01-31T05:00:00"), "DANGER"),
            (5, at("2026-01-31T06:00:00"), "CAUTION"),
            (5, at("2026-01-31T07:00:00"), "STABLE"),
        ]
        await connection.executemany(
            "INSERT INTO test_risk_evaluations VALUES ($1,$2,$3)", rows
        )
        day = date(2026, 1, 31)
        before = await connection.fetch("SELECT * FROM test_risk_counts ORDER BY id")
        preview = await workflow.reconcile_day(connection, day)
        assert preview["inserts"] == 4 and preview["updates"] == 2
        assert before == await connection.fetch(
            "SELECT * FROM test_risk_counts ORDER BY id"
        )
        result = await workflow.reconcile_day(connection, day, apply=True)
        assert result["written"] == 6
        saved = await connection.fetch(
            "SELECT * FROM test_risk_counts WHERE month='2026.01' ORDER BY ward_id"
        )
        assert [r["risk_days"] for r in saved] == [[2, 31], [], [31], [31], [31], []]
        assert [r["danger_stable_days"] for r in saved] == [
            [2, 31],
            [],
            [],
            [],
            [31],
            [],
        ]
        assert saved[0]["id"] == before[0]["id"]
        assert saved[0]["created_at"] == before[0]["created_at"]
        assert all(r["total_risk_count"] == len(r["risk_days"]) for r in saved)
        assert all(
            r["total_danger_stable_count"] == len(r["danger_stable_days"])
            for r in saved
        )
        assert (await workflow.reconcile_day(connection, day, apply=True))[
            "written"
        ] == 0
        assert saved == await connection.fetch(
            "SELECT * FROM test_risk_counts WHERE month='2026.01' ORDER BY ward_id"
        )
        assert before[2] == await connection.fetchrow(
            "SELECT * FROM test_risk_counts WHERE month='2025.12'"
        )
        # Late corrections remove this day's entries without losing another date.
        await connection.execute("DELETE FROM test_risk_evaluations WHERE ward_id=1")
        await workflow.reconcile_day(connection, day, apply=True)
        corrected = await connection.fetchrow(
            "SELECT * FROM test_risk_counts WHERE ward_id=1 AND month='2026.01'"
        )
        assert corrected["risk_days"] == corrected["danger_stable_days"] == [2]
    finally:
        await connection.close()
