import copy
import importlib.util
import json
import stat
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import pytest
from ax_contracts import NarrativeGenerationMetadata, WardWeeklyMetrics

from workflows.weekly_report.agents.reporter.fallback import build_fallback
from workflows.weekly_report.domain.derived_metrics import build_fact_package
from workflows.weekly_report.domain.rendering import render_report
from workflows.weekly_report.tools.source_repository import _mock_delta, _snapshot

SCRIPT = (
    Path(__file__).parents[2] / "playground/migrate-guardian-template-ids/migrate.py"
)
spec = importlib.util.spec_from_file_location("guardian_id_migration", SCRIPT)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def report(updates=None, previous_updates=None):
    updates = dict(updates or {})
    if "environment_out_of_range_days" in updates:
        updates["temperature_out_of_range_days"] = max(
            updates.get("low_temperature_days", 0),
            updates.get("high_temperature_days", 0),
        )
        updates["humidity_out_of_range_days"] = max(
            updates.get("low_humidity_days", 0), updates.get("high_humidity_days", 0)
        )
    if "device_power_count" in updates or "device_position_count" in updates:
        updates["device_good_count"] = (
            7
            - updates.get("device_power_count", 0)
            - updates.get("device_position_count", 0)
        )
    if updates.get("daily_summary_count") == 0:
        updates.update(
            device_good_count=None, device_power_count=None, device_position_count=None
        )
    current = _snapshot(101, current=True).model_copy(update=updates)
    previous = _snapshot(101, current=False).model_copy(update=previous_updates or {})
    metrics = WardWeeklyMetrics(
        ward_id=101,
        display_name="테스트",
        week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10),
        current=current,
        previous=previous,
        delta=_mock_delta(current, previous),
    )
    result = render_report(
        metrics,
        build_fallback(build_fact_package(metrics)),
        "template_fallback",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    ).template_data.model_dump(mode="json")
    for item in result["guardian_actions"]["items"]:
        if item["template_id"] and item["template_id"] != "GUI_GOOD_01":
            item["template_id"] = item["template_id"].removeprefix("GUI_")
    return result


@pytest.mark.parametrize(
    "updates,previous,expected",
    [
        (
            {"movement_count_total": 39},
            {"movement_count_total": 100},
            "GUI_ACT_RISK_01",
        ),
        (
            {"movement_count_total": 150},
            {"movement_count_total": 100},
            "GUI_ACT_RISK_02",
        ),
        (
            {"remote_control_count_total": 39},
            {"remote_control_count_total": 100},
            "GUI_ACT_RISK_03",
        ),
        (
            {"remote_control_count_total": 250},
            {"remote_control_count_total": 100},
            "GUI_ACT_RISK_04",
        ),
        (
            {"high_temperature_days": 2, "environment_out_of_range_days": 2},
            {},
            "GUI_ENV_CAUTION_01",
        ),
        (
            {"low_temperature_days": 2, "environment_out_of_range_days": 2},
            {},
            "GUI_ENV_CAUTION_02",
        ),
        (
            {"high_humidity_days": 2, "environment_out_of_range_days": 2},
            {},
            "GUI_ENV_CAUTION_03",
        ),
        (
            {"low_humidity_days": 2, "environment_out_of_range_days": 2},
            {},
            "GUI_ENV_CAUTION_04",
        ),
        (
            {
                "high_temperature_days": 4,
                "high_humidity_days": 4,
                "environment_out_of_range_days": 4,
            },
            {},
            "GUI_ENV_RISK_05",
        ),
        (
            {
                "high_temperature_days": 4,
                "low_humidity_days": 4,
                "environment_out_of_range_days": 4,
            },
            {},
            "GUI_ENV_RISK_06",
        ),
        (
            {
                "low_temperature_days": 4,
                "humidity_at_or_above_70_days": 4,
                "environment_out_of_range_days": 4,
            },
            {},
            "GUI_ENV_RISK_07",
        ),
        (
            {
                "low_temperature_days": 4,
                "low_humidity_days": 4,
                "environment_out_of_range_days": 4,
            },
            {},
            "GUI_ENV_RISK_08",
        ),
        ({"device_power_count": 2}, {}, "GUI_DEV_POWER_01"),
        ({"device_position_count": 2}, {}, "GUI_DEV_POS_01"),
    ],
)
def test_current_policy_selects_all_legacy_ids(updates, previous, expected):
    original = report(updates, previous)
    unchanged_copy = copy.deepcopy(original)
    plan, patched = migration.plan_report(original)
    assert plan["status"] == "update"
    assert patched["guardian_actions"]["items"][0]["template_id"] == expected
    assert original == unchanged_copy
    restored = copy.deepcopy(patched)
    for change in plan["changes"]:
        restored["guardian_actions"]["items"][change["item_index"]]["template_id"] = (
            change["before"]
        )
    assert (
        restored == original
    )  # No summaries, wording, metrics, dates, or other JSON changed.
    assert migration.plan_report(patched) == (
        {"status": "unchanged", "changes": []},
        None,
    )


def test_replacement_does_not_trust_old_id():
    data = report({"movement_count_total": 39}, {"movement_count_total": 100})
    data["guardian_actions"]["items"][0]["template_id"] = "ACT_RISK_04"
    plan, patched = migration.plan_report(data)
    assert plan["status"] == "update"
    assert patched["guardian_actions"]["items"][0]["template_id"] == "GUI_ACT_RISK_01"


@pytest.mark.parametrize("ratio", [40, 70, 149, 251])
def test_increase_card_requires_current_caution_increase(ratio):
    data = report({"movement_count_total": 200}, {"movement_count_total": 100})
    section = data["living_activity"]["activity_detection"]
    section["metrics"]["current_week"] = ratio
    section["status"] = migration._classify(ratio, 100).status
    plan, patched = migration.plan_report(data)
    assert plan == {
        "status": "blocked",
        "reason": "action_not_selected_by_current_policy",
    }
    assert patched is None


def test_changed_totals_with_stale_status_block_entire_report():
    data = report({"movement_count_total": 39}, {"movement_count_total": 100})
    data["living_activity"]["activity_detection"]["metrics"]["current_week"] = 200
    plan, patched = migration.plan_report(data)
    assert plan["reason"] == "activity_status_conflicts_with_totals"
    assert patched is None


@pytest.mark.parametrize("field,value", [("status", "GOOD"), ("tag", "unknown")])
def test_environment_condition_must_agree_with_card(field, value):
    data = report({"high_temperature_days": 4, "environment_out_of_range_days": 4})
    data["indoor_environment"][field] = value
    plan, patched = migration.plan_report(data)
    assert plan["status"] == "blocked"
    assert patched is None


def test_no_data_null_and_empty_parent_are_preserved():
    data = report({"daily_summary_count": 0, "device_count": 0, "covered_days": 0})
    assert data["guardian_actions"]["items"][0]["template_id"] is None
    original = copy.deepcopy(data)
    assert migration.plan_report(data) == ({"status": "unchanged", "changes": []}, None)
    assert data == original
    data["guardian_actions"].update(
        items=[], template_id="GUI_GOOD_01", empty_message="없어요."
    )
    assert migration.plan_report(data)[0]["status"] == "unchanged"


def test_stable_gui_good_01_is_preserved():
    data = report({"risk_detected_count": 0})
    assert data["guardian_actions"]["items"][0]["template_id"] == "GUI_GOOD_01"
    assert migration.plan_report(data)[0]["status"] == "unchanged"


@pytest.mark.parametrize("bad", [None, True, -1, float("nan"), float("inf"), "39"])
def test_invalid_or_missing_activity_evidence_is_not_renamed(bad):
    data = report({"movement_count_total": 39}, {"movement_count_total": 100})
    data["living_activity"]["activity_detection"]["metrics"]["current_week"] = bad
    assert migration.plan_report(data)[0]["status"] == "blocked"


def test_unrecognized_card_blocks_other_eligible_items():
    data = report(
        {"movement_count_total": 39, "remote_control_count_total": 39},
        {"movement_count_total": 100, "remote_control_count_total": 100},
    )
    data["guardian_actions"]["items"][1]["title"] = "Unknown"
    plan, patched = migration.plan_report(data)
    assert plan["status"] == "blocked"
    assert patched is None


def row(data, id=1):
    return {
        "id": id,
        "ward_id": 101,
        "week_start_date": date(2026, 8, 3),
        "week_end_date": date(2026, 8, 9),
        "updated_at": None,
        "report_data": json.dumps(data, ensure_ascii=False),
    }


class Database:
    def __init__(self, rows, output_dir, *, fail_at=None):
        self.rows = rows
        self.output_dir = output_dir
        self.fail_at = fail_at
        self.writes = []
        self.committed = False
        self.rolled_back = False

    @asynccontextmanager
    async def transaction(self, **kwargs):
        self.readonly = kwargs["readonly"]
        assert kwargs["isolation"] == "repeatable_read"
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise
        else:
            self.committed = True

    async def cursor(self, query, *args, **kwargs):
        self.query = query
        self.args = args
        assert ("FOR UPDATE" in query) is not self.readonly
        for record in self.rows:
            yield record

    async def execute(self, query, *args):
        assert not self.readonly
        # Every original and proposal is already persisted before the first UPDATE.
        artifact = next(self.output_dir.glob("*.jsonl"))
        records = [json.loads(line) for line in artifact.read_text().splitlines()]
        assert records[-1]["type"] == "planned"
        assert len([r for r in records if r.get("status") == "update"]) == len(
            self.rows
        )
        assert "report_data=$4::jsonb" in query
        assert "ward_id=$3" in query
        assert "updated_at=NOW()" in query
        self.writes.append((query, args))
        return "UPDATE 0" if len(self.writes) == self.fail_at else "UPDATE 1"


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["local", "live"])
@pytest.mark.parametrize("write", [False, True])
async def test_preview_or_write_targets_own_rows_with_backup(tmp_path, target, write):
    original = row(report({"movement_count_total": 39}, {"movement_count_total": 100}))
    db = Database([original], tmp_path)
    result = await migration.migrate(
        db, target=target, write=write, week_start=date(2026, 8, 3), output_dir=tmp_path
    )
    assert result == 0
    assert migration.TABLES[target] in db.query
    assert db.args == (date(2026, 8, 3),)
    assert len(db.writes) == int(write)
    assert db.committed
    artifact = next(tmp_path.glob("*.jsonl"))
    assert stat.S_IMODE(artifact.stat().st_mode) == 0o600
    records = [json.loads(line) for line in artifact.read_text().splitlines()]
    assert records[1]["original_row"]["report_data"] == original["report_data"]
    assert records[-1]["mode"] == ("committed" if write else "preview")


@pytest.mark.asyncio
async def test_failed_update_rolls_back_without_committed_receipt(tmp_path):
    data = report({"movement_count_total": 39}, {"movement_count_total": 100})
    db = Database([row(data), row(data, 2)], tmp_path, fail_at=2)
    with pytest.raises(ValueError, match="Concurrent change"):
        await migration.migrate(db, target="live", write=True, output_dir=tmp_path)
    assert db.rolled_back and not db.committed
    assert '"mode": "committed"' not in next(tmp_path.glob("*.jsonl")).read_text()


@pytest.mark.asyncio
@pytest.mark.parametrize("write", [False, True])
async def test_conflicts_abort_target_before_any_update(tmp_path, write):
    good = row(report({"movement_count_total": 39}, {"movement_count_total": 100}))
    bad = copy.deepcopy(good)
    bad["id"] = 2
    bad["week_end_date"] = date(2026, 8, 10)
    db = Database([good, bad], tmp_path)
    if write:
        with pytest.raises(ValueError, match="Blocked reports"):
            await migration.migrate(db, target="local", write=True, output_dir=tmp_path)
        assert db.rolled_back
    else:
        assert await migration.migrate(db, target="local", output_dir=tmp_path) == 2
    assert not db.writes


@pytest.mark.asyncio
async def test_backup_fsync_failure_prevents_writes(tmp_path, monkeypatch):
    db = Database(
        [row(report({"movement_count_total": 39}, {"movement_count_total": 100}))],
        tmp_path,
    )

    def fail(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(migration, "durable", fail)
    with pytest.raises(OSError):
        await migration.migrate(db, target="local", write=True, output_dir=tmp_path)
    assert not db.writes and db.rolled_back


def test_cli_preview_default_and_invalid_week():
    args = migration.parse_args([])
    assert args.target == "local" and not args.write
    with pytest.raises(SystemExit):
        migration.parse_args(["--week-start", "2026-10-20"])
