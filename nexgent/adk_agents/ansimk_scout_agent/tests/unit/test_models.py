from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import ScoutRunRequest, ScoutRunResponse


def test_scout_request_normalizes_topic_keywords_and_duplicates() -> None:
    request = ScoutRunRequest(
        topic="  Example research  ",
        keywords=[" alpha ", "ALPHA", "beta"],
        additional_instructions="  Focus on public-sector cases.  ",
    )

    assert request.topic == "Example research"
    assert request.keywords == ["alpha", "beta"]
    assert request.additional_instructions == "Focus on public-sector cases."


def test_scout_request_normalizes_blank_additional_instructions_to_none() -> None:
    request = ScoutRunRequest(
        topic="Example research",
        additional_instructions=" \n ",
    )

    assert request.additional_instructions is None


@pytest.mark.parametrize(
    "payload",
    [
        {"topic": "  "},
        {"topic": "ok", "keywords": [""]},
        {"topic": "valid topic", "keywords": ["x"] * 11},
        {"topic": "valid topic", "additional_instructions": "x" * 2_001},
        {"topic": "valid topic", "unknown": True},
    ],
)
def test_scout_request_rejects_invalid_input(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ScoutRunRequest.model_validate(payload)


def test_scout_response_validates_authoritative_terminal_metadata() -> None:
    response = ScoutRunResponse.model_validate(_response_payload())

    assert response.duration_seconds == 77.896
    assert response.source_count == len(response.sources)


@pytest.mark.parametrize(
    "updates",
    [
        {"started_at": "not-a-timestamp"},
        {"completed_at": "2026-08-28T01:29:59+00:00"},
        {"duration_seconds": -0.001},
        {"source_count": 2},
    ],
)
def test_scout_response_rejects_invalid_terminal_metadata(
    updates: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ScoutRunResponse.model_validate({**_response_payload(), **updates})


def _response_payload() -> dict[str, object]:
    return {
        "run_id": "0123456789abcdef0123456789abcdef",
        "status": "success",
        "started_at": "2026-08-28T01:30:00+00:00",
        "completed_at": "2026-08-28T01:31:17.896000+00:00",
        "duration_seconds": 77.896,
        "source_count": 1,
        "report": "# Scout Report",
        "sources": ["https://example.com/article"],
        "report_artifact": "runs/example/report.md",
        "log_artifact": "runs/example/execution.jsonl",
    }
