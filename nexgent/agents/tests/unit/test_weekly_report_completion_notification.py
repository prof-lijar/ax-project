import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from unittest.mock import Mock

import httpx
import pytest
from ax_integrations.notifications import NotificationError, submit_notification

from apps.weekly_report_scheduler import notification, pipeline
from apps.weekly_report_scheduler.notification import NotificationSettings
from apps.weekly_report_scheduler.submit import SchedulerSettings
from tests.unit.test_weekly_report_schedule_pipeline import job
from workflows.weekly_report.completion_notification import (
    REGIONS,
    collect_coverage,
    notification_payload,
)


def snapshot():
    return {
        "version": 1,
        "weeks": [
            {
                "week_start": start,
                "regions": {
                    region: {
                        "total": 40 if region == "전체" else 10,
                        "success": success * 4 if region == "전체" else success,
                    }
                    for region in REGIONS
                },
            }
            for start, success in [("2026-09-21", 9), ("2026-09-14", 8)]
        ],
    }


def test_native_table_preserves_every_region_count_rate_and_definition():
    payload = notification_payload(
        snapshot(), week_start="2026-09-21", destination="default"
    )
    assert "지난주 누락 4명 · 전주 대비 4명 감소" in payload["text"]
    assert "가입자 40명 중 36명 저장 완료" in payload["blocks"][1]["text"]["text"]
    assert "지난주 (2026/09/21~09/27)" in payload["blocks"][2]["elements"][0]["text"]
    assert "2주 전 (2026/09/14~09/20)" in payload["blocks"][2]["elements"][0]["text"]
    rows = [[cell["text"] for cell in row] for row in payload["blocks"][4]["rows"][1:]]
    assert len(rows) == 10 and all(len(row) == 7 for row in rows)
    assert [row[:2] for row in rows] == [
        [region, week] for region in REGIONS for week in ("지난주", "2주 전")
    ]
    assert rows[0] == ["전체", "지난주", "40", "36", "4", "10.00%", "10.00%p 감소"]
    assert rows[1] == ["전체", "2주 전", "40", "32", "8", "20.00%", "기준 주"]
    assert "퍼센트포인트" in payload["blocks"][-1]["text"]["text"]
    assert "과거 가입·탈퇴" in payload["blocks"][-1]["text"]["text"]
    assert "기존 저장 리포트도 성공에 포함" in payload["blocks"][-1]["text"]["text"]
    assert payload["locale"] == "ko" and payload["severity"] == "warning"


def test_empty_population_is_not_reported_as_zero_percent():
    data = snapshot()
    for week in data["weeks"]:
        for counts in week["regions"].values():
            counts.update(total=0, success=0)
    payload = notification_payload(data, week_start="2026-09-21", destination="default")
    assert "집계 대상 가입자가 없습니다" in payload["text"]
    assert [cell["text"] for cell in payload["blocks"][4]["rows"][1][-2:]] == [
        "산정 불가",
        "비교 불가",
    ]


@pytest.mark.parametrize(
    "success,label", [(7, "4명 증가"), (8, "변동 없음"), (10, "8명 감소")]
)
def test_korean_change_labels_and_complete_status(success, label):
    data = snapshot()
    for region, counts in data["weeks"][0]["regions"].items():
        counts["success"] = success * 4 if region == "전체" else success
    payload = notification_payload(data, week_start="2026-09-21", destination="default")
    assert f"전주 대비 {label}" in payload["text"]
    if success == 10:
        assert "가입자 40명 중 40명 저장 완료" in payload["blocks"][1]["text"]["text"]
        assert payload["severity"] == "success"


@pytest.mark.parametrize("change", ["negative", "overflow", "bool", "period", "sum"])
def test_invalid_snapshot_fails_closed(change):
    data = snapshot()
    counts = data["weeks"][0]["regions"]["전체"]
    if change == "period":
        data["weeks"][1]["week_start"] = "2026-09-21"
    else:
        counts["success"] = {"negative": -1, "overflow": 41, "bool": True, "sum": 35}[
            change
        ]
    with pytest.raises(ValueError):
        notification_payload(data, week_start="2026-09-21", destination="default")


@pytest.mark.asyncio
async def test_aggregate_snapshot_is_read_only_and_fills_absent_groups():
    class Connection:
        @asynccontextmanager
        async def transaction(self, **kwargs):
            assert kwargs == {"isolation": "repeatable_read", "readonly": True}
            yield

        async def fetch(self, query, week):
            assert week == date(2026, 9, 21)
            return [{"week_start": week, "region": "울진", "total": 3, "success": 2}]

    result = await collect_coverage(Connection(), date(2026, 9, 21))
    assert result["weeks"][0]["regions"]["전체"] == {"total": 3, "success": 2}
    assert result["weeks"][1]["regions"]["광명"] == {"total": 0, "success": 0}


def test_failed_notification_resumes_without_generation_or_migration(tmp_path):
    calls = []

    def collect(week, path):
        calls.append("coverage")
        path.write_text(json.dumps(snapshot()))

    send = Mock(
        side_effect=[
            NotificationError("offline"),
            {"id": "accepted", "status": "queued"},
        ]
    )
    settings = NotificationSettings(True, "http://backend:8000", "x" * 32)

    def notify(week, root):
        assert (
            root / f"{week}.json"
        ).exists()  # Migration receipt precedes submission.
        notification.notify_completed_week(
            week, root, settings=settings, collect=collect, send=send
        )

    kwargs = {
        "now": datetime(2026, 9, 27, 18, tzinfo=UTC),
        "state_root": tmp_path,
        "submit": Mock(return_value={**job("completed"), "week_start": "2026-09-21"}),
        "migrate": Mock(),
        "notify": notify,
    }
    with pytest.raises(NotificationError):
        pipeline.run_pipeline(SchedulerSettings(), **kwargs)
    frozen = json.loads((tmp_path / "2026-09-21.notification.json").read_text())
    assert "accepted" not in frozen
    # Subscriber/report changes must not alter an ambiguously accepted payload.
    (tmp_path / "2026-09-21.coverage.json").write_text("invalid new snapshot")
    pipeline.run_pipeline(SchedulerSettings(), **kwargs)
    pipeline.run_pipeline(SchedulerSettings(), **kwargs)
    kwargs["submit"].assert_called_once()
    kwargs["migrate"].assert_called_once_with("2026-09-21")
    assert calls == ["coverage"]
    assert send.call_count == 2
    assert send.call_args.args[0]["payload"] == frozen["payload"]


def test_failed_migration_never_notifies(tmp_path):
    notify = Mock()
    with pytest.raises(OSError):
        pipeline.run_pipeline(
            SchedulerSettings(),
            state_root=tmp_path,
            submit=Mock(return_value=job("completed")),
            migrate=Mock(side_effect=OSError),
            notify=notify,
        )
    notify.assert_not_called()


def test_backend_acceptance_before_local_ack_replays_identical_event(
    tmp_path, monkeypatch
):
    settings = NotificationSettings(True, "http://backend:8000", "x" * 32)
    payloads = []

    def send(event):
        payloads.append(json.dumps(event["payload"], sort_keys=True))
        return {"id": "accepted-id", "status": "queued"}

    def collect(week, path):
        path.write_text(json.dumps(snapshot()))

    original = notification.write_state

    def crash_on_ack(path, event):
        if event.get("accepted"):
            raise OSError("interrupted after backend accepted")
        original(path, event)

    monkeypatch.setattr(notification, "write_state", crash_on_ack)
    with pytest.raises(OSError):
        notification.notify_completed_week(
            "2026-09-21", tmp_path, settings=settings, collect=collect, send=send
        )
    monkeypatch.setattr(notification, "write_state", original)
    notification.notify_completed_week(
        "2026-09-21", tmp_path, settings=settings, collect=Mock(), send=send
    )
    assert payloads[0] == payloads[1]
    assert (
        json.loads((tmp_path / "2026-09-21.notification.json").read_text())["accepted"][
            "id"
        ]
        == "accepted-id"
    )


def test_snapshot_failure_preserves_migration_receipt_for_retry(tmp_path):
    collect = Mock(side_effect=OSError("database unavailable"))

    def notify(week, root):
        notification.notify_completed_week(
            week,
            root,
            settings=NotificationSettings(True, "http://backend", "x" * 32),
            collect=collect,
            send=Mock(),
        )

    with pytest.raises(OSError):
        pipeline.run_pipeline(
            SchedulerSettings(),
            now=datetime(2026, 9, 27, 18, tzinfo=UTC),
            state_root=tmp_path,
            submit=Mock(return_value=job("completed")),
            migrate=Mock(),
            notify=notify,
        )
    assert (tmp_path / "2026-09-21.json").exists()
    assert not (tmp_path / "2026-09-21.notification.json").exists()


def test_disabled_notifications_do_not_collect_or_submit(tmp_path):
    collect, send = Mock(), Mock()
    notification.notify_completed_week(
        "2026-09-21",
        tmp_path,
        settings=NotificationSettings(),
        collect=collect,
        send=send,
    )
    collect.assert_not_called()
    send.assert_not_called()


@pytest.mark.asyncio
async def test_backend_retry_reuses_auth_key_and_payload():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ReadTimeout("secret response", request=request)
        if len(requests) == 2:
            return httpx.Response(503)
        return httpx.Response(
            202,
            json={
                "id": "8ff04888-a682-4704-8d27-3d5cd2cb26cb",
                "status": "queued",
                "destination": "default",
            },
        )

    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await submit_notification(
            client,
            base_url="http://backend:8000",
            token="secret",
            key="weekly-report:production:2026-09-21:coverage-v1",
            payload={"destination": "default", "text": "완료"},
            sleep=sleep,
        )
    assert result["status"] == "queued"
    assert sleeps == [1, 2]
    assert len({r.content for r in requests}) == 1
    assert all(r.headers["authorization"] == "Bearer secret" for r in requests)
    assert len({r.headers["idempotency-key"] for r in requests}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body",
    [
        (401, {}),
        (409, {}),
        (302, {}),
        (202, {}),
        (
            202,
            {
                "id": "8ff04888-a682-4704-8d27-3d5cd2cb26cb",
                "status": "failed",
                "destination": "default",
            },
        ),
    ],
)
async def test_backend_rejections_are_safe_and_not_acknowledged(status, body):
    def handler(request):
        return httpx.Response(status, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(NotificationError) as error:
            await submit_notification(
                client,
                base_url="http://backend",
                token="secret",
                key="key",
                payload={"destination": "default"},
            )
    assert "secret" not in str(error.value)


def test_read_only_coverage_command_never_adds_write_flag(monkeypatch, tmp_path):
    command = Mock()
    process = Mock()
    process.__enter__ = Mock(return_value=process)
    process.__exit__ = Mock(return_value=False)
    process.wait.return_value = 0
    command.return_value = process
    monkeypatch.setattr(pipeline.subprocess, "Popen", command)
    pipeline.collect_production_coverage("2026-09-21", tmp_path / "coverage.json")
    args = command.call_args.args[0]
    assert "--write" not in args
    assert args[-2:] == ["--coverage-output", str(tmp_path / "coverage.json")]


def test_notification_config_reads_mounted_env_and_redacts_token(monkeypatch):
    for name in list(notification.os.environ):
        if name.startswith("WEEKLY_REPORT_NOTIFICATION_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(
        notification,
        "dotenv_values",
        lambda _: {
            "WEEKLY_REPORT_NOTIFICATION_ENABLED": "true",
            "WEEKLY_REPORT_NOTIFICATION_SERVICE_TOKEN": "s" * 32,
        },
    )
    settings = NotificationSettings.from_env()
    assert settings.enabled and settings.token == "s" * 32
    assert settings.token not in repr(settings)
    monkeypatch.setenv(
        "WEEKLY_REPORT_NOTIFICATION_API_URL", "http://user:password@backend"
    )
    with pytest.raises(ValueError, match="invalid notification configuration"):
        NotificationSettings.from_env()
