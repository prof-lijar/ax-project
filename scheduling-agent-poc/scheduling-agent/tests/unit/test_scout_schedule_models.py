from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.scout_schedule_models import (
    ScoutScheduleCreateRequest,
    ScoutScheduleRecurrence,
)

SEOUL = ZoneInfo("Asia/Seoul")


def future_local_iso(minutes: int = 10) -> str:
    return (
        (datetime.now(SEOUL) + timedelta(minutes=minutes))
        .replace(tzinfo=None, microsecond=0)
        .isoformat()
    )


def test_accepts_future_asia_seoul_wall_clock_time() -> None:
    request = ScoutScheduleCreateRequest(
        topic="고독사 예방 AI IoT 서비스 최근 동향",
        keywords=["AI 돌봄", "IoT 모니터링"],
        run_at=future_local_iso(),
        timezone="Asia/Seoul",
    )

    assert request.run_at.tzinfo is None
    assert request.trigger_at_utc.tzinfo is not None
    assert request.timezone == "Asia/Seoul"


def test_normalizes_topic_and_keywords_like_scout() -> None:
    request = ScoutScheduleCreateRequest(
        topic="  Scout topic  ",
        keywords=[" AI ", "ai", "IoT"],
        additional_instructions="  Organize findings by competitor.  ",
        run_at=future_local_iso(),
        timezone="Asia/Seoul",
    )

    assert request.topic == "Scout topic"
    assert request.keywords == ["AI", "IoT"]
    assert request.additional_instructions == "Organize findings by competitor."


def test_blank_additional_instructions_normalize_to_none() -> None:
    request = ScoutScheduleCreateRequest(
        topic="Scout topic",
        additional_instructions=" \n ",
        run_at=future_local_iso(),
        timezone="Asia/Seoul",
    )

    assert request.additional_instructions is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timezone", "UTC"),
        ("run_at", "not-a-datetime"),
        ("run_at", "2026-08-29T09:00:00+09:00"),
        ("run_at", "2026-08-29T09:00"),
    ],
)
def test_rejects_unsupported_or_malformed_schedule_values(
    field: str, value: str
) -> None:
    payload = {
        "topic": "A valid Scout topic",
        "keywords": [],
        "run_at": future_local_iso(),
        "timezone": "Asia/Seoul",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        ScoutScheduleCreateRequest.model_validate(payload)


def test_rejects_past_seoul_wall_clock_time() -> None:
    past = (datetime.now(SEOUL) - timedelta(seconds=1)).replace(
        tzinfo=None, microsecond=0
    )

    with pytest.raises(ValidationError, match="future"):
        ScoutScheduleCreateRequest(
            topic="A valid Scout topic",
            keywords=[],
            run_at=past.isoformat(),
            timezone="Asia/Seoul",
        )


@pytest.mark.parametrize(
    "payload_update",
    [
        {"topic": "  "},
        {"keywords": [""]},
        {"keywords": ["x" * 101]},
        {"keywords": [str(index) for index in range(11)]},
        {"additional_instructions": "x" * 2_001},
    ],
)
def test_rejects_invalid_scout_topic_or_keywords(
    payload_update: dict[str, object],
) -> None:
    payload: dict[str, object] = {
        "topic": "A valid Scout topic",
        "keywords": [],
        "run_at": future_local_iso(),
        "timezone": "Asia/Seoul",
    }
    payload.update(payload_update)

    with pytest.raises(ValidationError):
        ScoutScheduleCreateRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("recurrence", "fields"),
    [
        ("daily", {"schedule_time": "09:15"}),
        (
            "weekly",
            {"schedule_time": "10:30:00", "day_of_week": "wednesday"},
        ),
        ("monthly", {"schedule_time": "18:45", "day_of_month": 31}),
    ],
)
def test_accepts_recurring_seoul_wall_clock_rules(
    recurrence: str, fields: dict[str, object]
) -> None:
    request = ScoutScheduleCreateRequest.model_validate(
        {
            "topic": "A recurring Scout topic",
            "keywords": [],
            "recurrence": recurrence,
            "timezone": "Asia/Seoul",
            **fields,
        }
    )

    assert request.recurrence.value == recurrence
    assert request.run_at is None
    assert request.schedule_time is not None


def test_omitted_recurrence_preserves_once_contract() -> None:
    request = ScoutScheduleCreateRequest(
        topic="A valid Scout topic",
        keywords=[],
        run_at=future_local_iso(),
        timezone="Asia/Seoul",
    )

    assert request.recurrence is ScoutScheduleRecurrence.ONCE


@pytest.mark.parametrize(
    "payload",
    [
        {"recurrence": "daily"},
        {"recurrence": "daily", "schedule_time": "09:00", "run_at": "future"},
        {"recurrence": "weekly", "schedule_time": "09:00"},
        {
            "recurrence": "weekly",
            "schedule_time": "09:00",
            "day_of_week": "monday",
            "day_of_month": 1,
        },
        {"recurrence": "monthly", "schedule_time": "09:00"},
        {"recurrence": "monthly", "schedule_time": "09:00", "day_of_month": 32},
    ],
)
def test_rejects_incomplete_or_mixed_recurring_rules(
    payload: dict[str, object],
) -> None:
    if payload.get("run_at") == "future":
        payload = {**payload, "run_at": future_local_iso()}
    with pytest.raises(ValidationError):
        ScoutScheduleCreateRequest.model_validate(
            {
                "topic": "A recurring Scout topic",
                "keywords": [],
                "timezone": "Asia/Seoul",
                **payload,
            }
        )
