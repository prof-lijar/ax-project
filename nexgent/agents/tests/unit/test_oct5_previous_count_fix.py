import copy
import importlib.util
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import pytest

from workflows.weekly_report.domain.activity_policy import activity_status_label

SCRIPT = Path(__file__).parents[2] / "playground/fix-oct5-previous-counts/fix.py"
spec = importlib.util.spec_from_file_location("oct5_count_fix", SCRIPT)
fix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix)


def report(week, actual=(8193, 3175), previous=(6833, 2747), ward_id=12007):
    activity = {"descriptions": ["Existing qualitative guidance"], "tag": "preserved"}
    for key, value, prior in zip(fix.SIGNALS, actual, previous, strict=True):
        assessment = fix._classify(value, prior)
        activity[key] = {
            "status": activity_status_label(assessment),
            "metrics": {
                "current_week": value,
                "current_week_display": f"{value}회",
                "previous_week": prior,
                "previous_week_display": str(prior),
                "comparison_percent": assessment.ratio_percent,
                "comparison_display": fix._percentage(assessment),
            },
        }
    data = {
        "basic_info": {"period": {"start_date": str(week), "end_date": str(week + timedelta(days=6))}},
        "living_activity": activity,
        "weekly_summary": "Existing summary",
        "guardian_actions": {"items": [{"template_id": "GUI_GOOD_01"}]},
        "unknown_future_field": {"keep": [1, 2]},
    }
    return {
        "ward_id": ward_id, "week_start_date": week,
        "week_end_date": week + timedelta(days=6), "weekly_score": 100,
        "weekly_status": "GOOD", "report_data": json.dumps(data),
        "created_at": None, "updated_at": None,
    }


def baseline(**kwargs):
    return report(fix.BASELINE_WEEK, actual=(6009, 2339), **kwargs)


def test_investigated_ward_only_comparison_fields_change_and_retry_is_noop():
    current, prior = report(fix.WEEK), baseline()
    snapshot = copy.deepcopy((current, prior))
    plan, patched = fix.plan_report(current, prior)
    assert plan["status"] == "update"
    assert (current, prior) == snapshot
    original = json.loads(current["report_data"])
    for key, expected_prior, percent in zip(fix.SIGNALS, (6009, 2339), ("136.3%", "135.7%"), strict=True):
        metrics = patched["living_activity"][key]["metrics"]
        assert metrics["previous_week"] == expected_prior
        assert metrics["previous_week_display"] == f"{expected_prior}회"
        assert metrics["comparison_display"] == percent
        assert metrics["comparison_percent"] == pytest.approx(metrics["current_week"] * 100 / expected_prior)
        # Restore the four allowed changes; the rest of the document must match.
        for field in ("previous_week", "previous_week_display", "comparison_percent", "comparison_display"):
            original["living_activity"][key]["metrics"][field] = metrics[field]
    assert patched == original
    current["report_data"] = json.dumps(patched)
    assert fix.plan_report(current, prior)[0]["status"] == "unchanged"


@pytest.mark.parametrize("actual,old_prior,new_prior", [(100, 100, 300), (100, 200, 50), (100, 100, 0), (100, 100, None)])
def test_status_or_trend_change_still_copies_counts_and_preserves_content(actual, old_prior, new_prior):
    current = report(fix.WEEK, actual=(actual, 3175), previous=(old_prior, 2747))
    prior = report(fix.BASELINE_WEEK, actual=(new_prior, 2339))
    plan, patched = fix.plan_report(current, prior)
    assert plan["status"] == "update"
    original = json.loads(current["report_data"])
    for signal, expected in zip(fix.SIGNALS, (new_prior, 2339), strict=True):
        assert patched["living_activity"][signal]["metrics"]["previous_week"] == expected
        for field in ("previous_week", "previous_week_display", "comparison_percent", "comparison_display"):
            original["living_activity"][signal]["metrics"][field] = patched["living_activity"][signal]["metrics"][field]
    assert patched == original
    # Preserved classifications must never cause a rerun to reject the report.
    current["report_data"] = json.dumps(patched)
    assert fix.plan_report(current, prior)[0]["status"] == "unchanged"


def test_already_unavailable_baseline_remains_unavailable():
    current = report(fix.WEEK, previous=(0, None))
    prior = report(fix.BASELINE_WEEK, actual=(None, 0))
    plan, patched = fix.plan_report(current, prior)
    assert plan["status"] == "update"
    for signal in fix.SIGNALS:
        metrics = patched["living_activity"][signal]["metrics"]
        assert metrics["comparison_percent"] is None
        assert metrics["comparison_display"] == "비교 불가"


@pytest.mark.parametrize("bad", [True, "6009", -1, float("inf"), float("nan")])
def test_invalid_baseline_count_is_not_written(bad):
    prior = baseline()
    data = json.loads(prior["report_data"])
    data["living_activity"][fix.SIGNALS[0]]["metrics"]["current_week"] = bad
    prior["report_data"] = data
    assert fix.plan_report(report(fix.WEEK), prior) == ({"ward_id": 12007, "status": "invalid_report"}, None)


@pytest.mark.parametrize("error", ["missing_key", "period", "row_period", "json"])
def test_reject_inconsistent_report(error):
    current = report(fix.WEEK)
    data = json.loads(current["report_data"])
    if error == "missing_key":
        del data["living_activity"][fix.SIGNALS[0]]["metrics"]["current_week"]
    elif error == "period":
        data["basic_info"]["period"]["start_date"] = "2026-10-06"
    elif error == "row_period":
        current["week_end_date"] = fix.WEEK
    current["report_data"] = "{" if error == "json" else json.dumps(data)
    assert fix.plan_report(current, baseline())[0]["status"] == "invalid_report"


def test_existing_classification_does_not_block_copy():
    current = report(fix.WEEK)
    data = json.loads(current["report_data"])
    data["living_activity"][fix.SIGNALS[0]]["status"] = "RISK"
    current["report_data"] = json.dumps(data)
    plan, patched = fix.plan_report(current, baseline())
    assert plan["status"] == "update"
    assert patched["living_activity"][fix.SIGNALS[0]]["status"] == "RISK"
    assert patched["living_activity"][fix.SIGNALS[0]]["metrics"]["previous_week"] == 6009


class Database:
    def __init__(self, rows, directory, fail=False):
        self.rows = rows
        self.directory = directory
        self.fail = fail
        self.writes = []
        self.rolled_back = False

    @asynccontextmanager
    async def transaction(self, **kwargs):
        self.readonly = kwargs["readonly"]
        assert kwargs["isolation"] == "repeatable_read"
        snapshot = copy.deepcopy(self.rows)
        try:
            yield
        except Exception:
            self.rows = snapshot
            self.rolled_back = True
            raise

    async def fetch(self, query, *args):
        assert args == (fix.BASELINE_WEEK, fix.WEEK)
        assert ("FOR UPDATE" in query) == (not self.readonly)
        return self.rows

    async def execute(self, query, ward, week, patched, original):
        assert not self.readonly
        # The complete original snapshot must be on disk before the first write.
        artifacts = list(self.directory.glob("*.json"))
        assert len(artifacts) == 1
        backup = json.loads(artifacts[0].read_text())
        assert backup["mode"] == "pre_write_backup"
        assert len(backup["original_rows"]) == len(self.rows)
        assert artifacts[0].stat().st_mode & 0o777 == 0o600
        self.writes.append(ward)
        for row in self.rows:
            if row["ward_id"] == ward and row["week_start_date"] == week:
                assert row["report_data"] == original
                row["report_data"] = patched
        return "UPDATE 0" if self.fail else "UPDATE 1"


@pytest.mark.asyncio
@pytest.mark.parametrize("write", [False, True])
async def test_all_wards_preview_or_commit_and_missing_baseline_is_explicit(tmp_path, write):
    rows = [report(fix.WEEK), baseline(), report(fix.WEEK, ward_id=99)]
    db = Database(copy.deepcopy(rows), tmp_path)
    code = await fix.correct(db, write=write, output_dir=tmp_path)
    assert code == 2  # The missing baseline never appears as complete success.
    assert db.writes == ([12007] if write else [])
    assert db.rows[1:] == rows[1:]
    if not write:
        assert db.rows == rows
    backup = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert backup["counts"] == {"update": 1, "missing_baseline": 1}


@pytest.mark.asyncio
async def test_failed_update_rolls_back_and_never_prints_committed(tmp_path, capsys):
    rows = [report(fix.WEEK), baseline()]
    db = Database(copy.deepcopy(rows), tmp_path, fail=True)
    with pytest.raises(ValueError, match="rolled back"):
        await fix.correct(db, write=True, output_dir=tmp_path)
    assert db.rows == rows
    assert db.rolled_back
    assert '"mode": "committed"' not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_backup_failure_prevents_writes(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(fix, "save_artifact", fail)
    db = Database([report(fix.WEEK), baseline()], tmp_path)
    with pytest.raises(OSError):
        await fix.correct(db, write=True, output_dir=tmp_path)
    assert db.writes == []
    assert db.rolled_back


@pytest.mark.asyncio
async def test_no_october_rows_fails_without_write(tmp_path):
    db = Database([baseline()], tmp_path)
    with pytest.raises(ValueError, match="No October"):
        await fix.correct(db, write=True, output_dir=tmp_path)
    assert db.writes == []


def test_backup_paths_are_unique_and_preserve_prior_artifacts(tmp_path):
    first = fix.save_artifact(tmp_path, {"first": True})
    second = fix.save_artifact(tmp_path, {"second": True})
    assert first != second
    assert json.loads(first.read_text()) == {"first": True}
