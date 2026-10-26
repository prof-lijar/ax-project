"""Synthetic tests; no external services or production data."""

import asyncio
import copy
import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from io import StringIO
from pathlib import Path

spec = importlib.util.spec_from_file_location("oct12_fix", Path(__file__).with_name("fix.py"))
fix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix)


def row(week, current=100, previous=200, ward=1):
    end = week + timedelta(days=6)
    return {
        "ward_id": ward, "week_start_date": week, "week_end_date": end,
        "report_data": {
            "basic_info": {"period": {"start_date": str(week), "end_date": str(end)}},
            "summary": "preserve this text",
            "living_activity": {
                signal: {"status": "GOOD", "metrics": {
                    "current_week": current, "previous_week": previous,
                    "current_week_display": "stale", "previous_week_display": "preserve",
                    "comparison_percent": 999, "comparison_display": "stale",
                }} for signal in fix.SIGNALS
            },
        },
    }


class PlanTests(unittest.TestCase):
    def test_direction_derived_fields_and_preservation(self):
        target = row(fix.WEEK)
        source = row(fix.SOURCE_WEEK, current=9999, previous=150)
        source["report_data"]["living_activity"][fix.SIGNALS[1]]["metrics"]["previous_week"] = 400
        originals = copy.deepcopy((target, source))
        plan, patched = fix.plan_report(target, source)
        self.assertEqual(plan["status"], "update")
        expected = copy.deepcopy(target["report_data"])
        for signal, value, percent in zip(fix.SIGNALS, (150, 400), (75, 200)):
            expected["living_activity"][signal]["metrics"].update(
                current_week=value, current_week_display=f"{value}회",
                comparison_percent=percent, comparison_display=f"{percent}%",
            )
        self.assertEqual(patched, expected)
        self.assertEqual((target, source), originals)
        self.assertEqual(plan["changes"][fix.SIGNALS[0]]["classification_after"], ["GOOD", "stable"])
        target["report_data"] = patched
        self.assertEqual(fix.plan_report(target, source)[0]["status"], "unchanged")

    def test_missing_source(self):
        self.assertEqual(fix.plan_report(row(fix.WEEK), None),
                         ({"ward_id": 1, "status": "missing_source"}, None))

    def test_invalid_signal_skips_entire_ward(self):
        for value in (-1, True, "12", float("nan"), float("inf")):
            with self.subTest(value=value):
                source = row(fix.SOURCE_WEEK)
                source["report_data"]["living_activity"][fix.SIGNALS[1]]["metrics"]["previous_week"] = value
                plan, patched = fix.plan_report(row(fix.WEEK), source)
                self.assertEqual(plan["status"], "invalid_report")
                self.assertIsNone(patched)

    def test_missing_field_and_bad_period(self):
        for problem in ("missing", "json_date", "row_date", "malformed_json"):
            with self.subTest(problem=problem):
                source = row(fix.SOURCE_WEEK)
                if problem == "missing":
                    del source["report_data"]["living_activity"][fix.SIGNALS[0]]["metrics"]["previous_week"]
                elif problem == "json_date":
                    source["report_data"]["basic_info"]["period"]["start_date"] = str(fix.WEEK)
                elif problem == "row_date":
                    source["week_end_date"] += timedelta(days=1)
                else:
                    source["report_data"] = "{"
                self.assertEqual(fix.plan_report(row(fix.WEEK), source)[0]["status"], "invalid_report")

    def test_null_and_zero(self):
        for actual, previous, percent in ((None, 200, None), (0, 200, 0), (150, 0, None), (150, None, None)):
            with self.subTest(actual=actual, previous=previous):
                _, patched = fix.plan_report(row(fix.WEEK, previous=previous), row(fix.SOURCE_WEEK, previous=actual))
                metrics = patched["living_activity"][fix.SIGNALS[0]]["metrics"]
                self.assertEqual(metrics["current_week"], actual)
                self.assertEqual(metrics["comparison_percent"], percent)
                if percent is None:
                    self.assertEqual(metrics["comparison_display"], "비교 불가")

    def test_json_string_rows(self):
        target, source = row(fix.WEEK), row(fix.SOURCE_WEEK)
        target["report_data"] = json.dumps(target["report_data"])
        source["report_data"] = json.dumps(source["report_data"])
        self.assertEqual(fix.plan_report(target, source)[0]["status"], "update")


class FakeConnection:
    def __init__(self, outcome="UPDATE 1"):
        self.rows = [row(fix.WEEK), row(fix.SOURCE_WEEK), row(fix.WEEK, ward=2)]
        self.outcome = outcome
        self.calls = []
        self.committed = False

    def transaction(self, **options):
        self.options = options
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, kind, value, trace):
        self.committed = kind is None

    async def fetch(self, sql, *args):
        self.query = sql
        return self.rows

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return self.outcome


class TransactionTests(unittest.TestCase):
    def test_preview_and_write(self):
        for write in (False, True):
            with self.subTest(write=write), tempfile.TemporaryDirectory() as directory:
                connection = FakeConnection()
                output = StringIO()
                with redirect_stdout(output):
                    code = asyncio.run(fix.correct(connection, write=write, output_dir=Path(directory)))
                self.assertEqual(code, 2)  # Ward 2 has no source.
                self.assertEqual(len(connection.calls), int(write))
                self.assertEqual(connection.options["readonly"], not write)
                self.assertEqual("FOR UPDATE" in connection.query, write)
                self.assertTrue(connection.committed)
                artifact = next(Path(directory).glob("*.json"))
                self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
                backup = json.loads(artifact.read_text())
                self.assertEqual(len(backup["original_rows"]), 3)
                self.assertEqual(backup["source_week_start"], "2026-10-19")
                if write:
                    self.assertEqual(connection.calls[0][1][1], fix.WEEK)
                    self.assertIn('"mode": "committed"', output.getvalue())

    def test_conflict_aborts_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = FakeConnection(outcome="UPDATE 0")
            output = StringIO()
            with redirect_stdout(output), self.assertRaises(ValueError):
                asyncio.run(fix.correct(connection, write=True, output_dir=Path(directory)))
            self.assertFalse(connection.committed)
            self.assertNotIn('"mode": "committed"', output.getvalue())
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
