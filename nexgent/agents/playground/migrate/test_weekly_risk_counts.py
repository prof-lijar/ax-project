import argparse
import contextlib
import io
import json
import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import migrate_weekly_risk_counts as migration
from migrate_weekly_risk_counts import (
    month_bounds,
    months_between,
    parse_month,
)


class DatabaseSettingsTests(unittest.TestCase):
    def resolve(self, environment, agent_env):
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(migration, "dotenv_values", return_value=agent_env),
        ):
            return migration.source_database_dsn()

    def test_explicit_source_override(self):
        self.assertEqual(
            self.resolve(
                {"SOURCE_DATABASE_DSN": "postgresql://source"},
                {"WEEKLY_REPORT_STORAGE_DATABASE_DSN": "postgresql://storage"},
            ),
            "postgresql://source",
        )

    def test_blank_source_uses_storage_setting(self):
        self.assertEqual(
            self.resolve(
                {"SOURCE_DATABASE_DSN": " "},
                {
                    "WEEKLY_REPORT_STORAGE_DATABASE_DSN": "postgresql://storage",
                    "ANSIMK_DATABASE_DSN": "postgresql://fallback",
                },
            ),
            "postgresql://storage",
        )

    def test_exported_storage_overrides_file(self):
        self.assertEqual(
            self.resolve(
                {"WEEKLY_REPORT_STORAGE_DATABASE_DSN": "postgresql://exported"},
                {"WEEKLY_REPORT_STORAGE_DATABASE_DSN": "postgresql://file"},
            ),
            "postgresql://exported",
        )

    def test_ansimk_fallback(self):
        self.assertEqual(
            self.resolve({}, {"ANSIMK_DATABASE_DSN": "postgresql://fallback"}),
            "postgresql://fallback",
        )

    def test_missing_settings_fail(self):
        with self.assertRaises(ValueError):
            self.resolve({}, {})


class MonthBoundaryTests(unittest.TestCase):
    def test_both_input_formats(self):
        for value in ("2026-07", "2026.07"):
            self.assertEqual(parse_month(value), date(2026, 7, 1))

    def test_invalid_months(self):
        for value in (
            "2026-7",
            "2026-00",
            "2026-13",
            "0000-01",
            "9999-12",
            "2026-07-01",
            "2026/07",
        ):
            with (
                self.subTest(value=value),
                self.assertRaises(argparse.ArgumentTypeError),
            ):
                parse_month(value)

    def test_inclusive_range_crosses_year(self):
        self.assertEqual(
            list(months_between(date(2025, 12, 1), date(2026, 2, 1))),
            [date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)],
        )

    def test_single_month(self):
        month = date(2026, 7, 1)
        self.assertEqual(list(months_between(month, month)), [month])

    def test_seoul_boundaries_in_utc(self):
        start, end = month_bounds(date(2026, 7, 1), ZoneInfo("Asia/Seoul"))
        self.assertEqual(
            start.astimezone(timezone.utc),
            datetime(2026, 6, 30, 15, tzinfo=timezone.utc),
        )
        self.assertEqual(
            end.astimezone(timezone.utc),
            datetime(2026, 7, 31, 15, tzinfo=timezone.utc),
        )

    def test_leap_february(self):
        start, end = month_bounds(date(2024, 2, 1), ZoneInfo("Asia/Seoul"))
        self.assertEqual((end - start).days, 29)

    def test_dst_month_uses_local_midnight(self):
        start, end = month_bounds(date(2026, 3, 1), ZoneInfo("America/New_York"))
        self.assertEqual(start.astimezone(timezone.utc).hour, 5)
        self.assertEqual(end.astimezone(timezone.utc).hour, 4)


class AutomaticRangeTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_history_uses_local_months_and_includes_gaps(self):
        connection = AsyncMock()
        connection.fetchrow.return_value = {
            "first_evaluation": datetime(2025, 12, 31, 15, tzinfo=timezone.utc),
            "last_evaluation": datetime(2026, 3, 31, 15, tzinfo=timezone.utc),
        }
        start, end = await migration.resolve_month_range(
            connection, None, None, ZoneInfo("Asia/Seoul")
        )
        self.assertEqual(start, date(2026, 1, 1))
        self.assertEqual(end, date(2026, 4, 1))
        self.assertEqual(len(list(months_between(start, end))), 4)

    async def test_empty_source_has_no_range(self):
        connection = AsyncMock()
        connection.fetchrow.return_value = {
            "first_evaluation": None,
            "last_evaluation": None,
        }
        self.assertIsNone(
            await migration.resolve_month_range(
                connection, None, None, ZoneInfo("Asia/Seoul")
            )
        )

    async def test_explicit_range_does_not_query_source_bounds(self):
        connection = AsyncMock()
        start, end = date(2026, 9, 1), date(2026, 10, 1)
        self.assertEqual(
            await migration.resolve_month_range(
                connection, start, end, ZoneInfo("Asia/Seoul")
            ),
            (start, end),
        )
        connection.fetchrow.assert_not_awaited()

    def test_cli_without_months_keeps_preview_default(self):
        _, args = migration.parse_args([])
        self.assertIsNone(args.start_month)
        self.assertIsNone(args.end_month)
        self.assertFalse(args.apply)
        _, args = migration.parse_args(["--apply"])
        self.assertTrue(args.apply)

    def test_partial_or_reversed_ranges_are_rejected(self):
        for argv in (
            ["--start-month", "2026-09"],
            ["--end-month", "2026-10"],
            ["--start-month", "2026-10", "--end-month", "2026-09"],
        ):
            with (
                self.subTest(argv=argv),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                migration.parse_args(argv)
            self.assertEqual(error.exception.code, 2)


class ProgressTests(unittest.IsolatedAsyncioTestCase):
    def connection(self):
        connection = AsyncMock()
        transaction = AsyncMock()
        connection.transaction = MagicMock(return_value=transaction)
        connection.fetchrow.return_value = {
            "wards": 3,
            "inserts": 1,
            "updates": 1,
            "danger_days": 8,
            "danger_stable_days": 2,
        }
        connection.fetchval.return_value = 2
        return connection, transaction

    async def test_commit_receipt_reports_month_progress(self):
        connection, _ = self.connection()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            await migration.migrate(
                connection,
                date(2026, 9, 1),
                date(2026, 10, 1),
                ZoneInfo("Asia/Seoul"),
                apply=True,
            )
        receipts = [
            json.loads(line)
            for line in output.getvalue().splitlines()
            if line.startswith("{")
        ]
        self.assertEqual([row["progress_percent"] for row in receipts], [50, 100])
        self.assertEqual([row["mode"] for row in receipts], ["committed"] * 2)
        self.assertIn("[1/2] 2026.09 Writing", output.getvalue())
        self.assertIn("Migration complete: 2/2 months", output.getvalue())

    async def test_failed_commit_does_not_report_success(self):
        connection, transaction = self.connection()
        transaction.__aexit__.side_effect = RuntimeError("fixture commit failure")
        output, errors = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(errors),
            self.assertRaises(RuntimeError),
        ):
            await migration.migrate(
                connection,
                date(2026, 9, 1),
                date(2026, 9, 1),
                ZoneInfo("Asia/Seoul"),
                apply=True,
            )
        self.assertNotIn('"mode": "committed"', output.getvalue())
        self.assertNotIn("Migration complete", output.getvalue())
        self.assertIn("[1/1] 2026.09 Processing month — failed", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
