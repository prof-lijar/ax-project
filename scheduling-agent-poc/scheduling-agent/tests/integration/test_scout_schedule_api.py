from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from app import scheduler_service as legacy_scheduler_service
from app.fast_api_app import create_app
from app.scout_schedule_models import ScoutScheduleStatus
from app.scout_schedule_service import ScoutScheduleService, ScoutScheduleSettings

SEOUL = ZoneInfo("Asia/Seoul")


class NoopScoutClient:
    def close(self) -> None:
        pass


def future_local_iso(minutes: int = 10) -> str:
    return (
        (datetime.now(SEOUL) + timedelta(minutes=minutes))
        .replace(tzinfo=None, microsecond=0)
        .isoformat()
    )


def build_test_service(tmp_path: Path) -> ScoutScheduleService:
    return ScoutScheduleService(
        ScoutScheduleSettings(
            database_path=tmp_path / "api.sqlite3",
            misfire_grace_seconds=10,
        ),
        scout_client=NoopScoutClient(),
        scheduler=BackgroundScheduler(),
    )


def valid_payload() -> dict[str, object]:
    return {
        "topic": "고독사 예방 AI IoT 서비스 최근 동향",
        "keywords": ["고독사 예방", "AI 돌봄", "IoT 모니터링"],
        "additional_instructions": "Focus on public-sector deployment cases.",
        "run_at": future_local_iso(),
        "timezone": "Asia/Seoul",
    }


@pytest.mark.asyncio
async def test_post_get_and_delete_preserve_schedule_history(tmp_path: Path) -> None:
    service = build_test_service(tmp_path)
    api = create_app(scout_service_factory=lambda: service)
    api.state.scout_schedule_service = service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://test"
    ) as client:
        create_response = await client.post("/v1/scout/schedules", json=valid_payload())
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["status"] == "pending"
        assert created["recurrence"] == "once"
        assert created["additional_instructions"] == (
            "Focus on public-sector deployment cases."
        )

        list_response = await client.get("/v1/scout/schedules")
        assert list_response.status_code == 200
        assert [item["schedule_id"] for item in list_response.json()["schedules"]] == [
            created["schedule_id"]
        ]

        cancel_response = await client.delete(
            f"/v1/scout/schedules/{created['schedule_id']}"
        )
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "cancelled"

        history = (await client.get("/v1/scout/schedules")).json()["schedules"]
        assert len(history) == 1
        assert history[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_duplicate_pending_submission_is_rejected_safely(tmp_path: Path) -> None:
    service = build_test_service(tmp_path)
    api = create_app(scout_service_factory=lambda: service)
    api.state.scout_schedule_service = service
    payload = valid_payload()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://test"
    ) as client:
        assert (
            await client.post("/v1/scout/schedules", json=payload)
        ).status_code == 201
        duplicate = await client.post("/v1/scout/schedules", json=payload)

    assert duplicate.status_code == 409
    assert "traceback" not in duplicate.text.lower()


@pytest.mark.parametrize(
    ("recurrence", "fields"),
    [
        ("daily", {"schedule_time": "09:15:00"}),
        (
            "weekly",
            {"schedule_time": "10:30:00", "day_of_week": "friday"},
        ),
        ("monthly", {"schedule_time": "18:45:00", "day_of_month": 31}),
    ],
)
@pytest.mark.asyncio
async def test_post_accepts_recurring_schedule_contract(
    tmp_path: Path,
    recurrence: str,
    fields: dict[str, object],
) -> None:
    service = build_test_service(tmp_path)
    api = create_app(scout_service_factory=lambda: service)
    api.state.scout_schedule_service = service
    payload = {
        "topic": "A recurring Scout topic",
        "keywords": ["AI"],
        "recurrence": recurrence,
        "timezone": "Asia/Seoul",
        **fields,
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.post("/v1/scout/schedules", json=payload)

    assert response.status_code == 201
    record = response.json()
    assert record["recurrence"] == recurrence
    assert record["run_at"]
    assert record["trigger_at"].endswith(("Z", "+00:00"))
    assert record["schedule_time"] == fields["schedule_time"]


@pytest.mark.asyncio
async def test_delete_rejects_running_or_terminal_and_unknown_schedules(
    tmp_path: Path,
) -> None:
    service = build_test_service(tmp_path)
    api = create_app(scout_service_factory=lambda: service)
    api.state.scout_schedule_service = service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://test"
    ) as client:
        created = (
            await client.post("/v1/scout/schedules", json=valid_payload())
        ).json()
        service.repository.claim_pending(created["schedule_id"])

        running_response = await client.delete(
            f"/v1/scout/schedules/{created['schedule_id']}"
        )
        assert running_response.status_code == 409
        assert (
            service.repository.get(created["schedule_id"]).status
            is ScoutScheduleStatus.RUNNING
        )

        unknown_response = await client.delete(
            "/v1/scout/schedules/00000000-0000-0000-0000-000000000000"
        )
        assert unknown_response.status_code == 404


@pytest.mark.parametrize(
    "payload_update",
    [
        {"timezone": "UTC"},
        {"run_at": "bad-value"},
        {
            "run_at": (datetime.now(SEOUL) - timedelta(minutes=1))
            .replace(tzinfo=None, microsecond=0)
            .isoformat()
        },
        {"topic": " "},
        {"additional_instructions": "x" * 2_001},
    ],
)
@pytest.mark.asyncio
async def test_create_validation_errors_are_safe(
    tmp_path: Path, payload_update: dict[str, object]
) -> None:
    service = build_test_service(tmp_path)
    api = create_app(scout_service_factory=lambda: service)
    api.state.scout_schedule_service = service
    payload = valid_payload()
    payload.update(payload_update)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.post("/v1/scout/schedules", json=payload)

    assert response.status_code == 422
    assert "traceback" not in response.text.lower()


@pytest.mark.asyncio
async def test_partial_lifespan_failure_stops_owned_legacy_scheduler_safely() -> None:
    class FailingScoutService:
        shutdown_called = False

        def start(self) -> None:
            raise RuntimeError("startup failed")

        def shutdown(self) -> None:
            self.shutdown_called = True

    failing_service = FailingScoutService()
    api = create_app(scout_service_factory=lambda: failing_service)  # type: ignore[arg-type]

    assert legacy_scheduler_service.scheduler.running is False

    with pytest.raises(RuntimeError, match="startup failed"):
        async with api.router.lifespan_context(api):
            pass

    assert legacy_scheduler_service.scheduler.running is False
    assert failing_service.shutdown_called is False
