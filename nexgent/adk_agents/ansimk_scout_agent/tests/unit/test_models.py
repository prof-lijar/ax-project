from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import ScoutRunRequest


def test_scout_request_normalizes_topic_keywords_and_duplicates() -> None:
    request = ScoutRunRequest(
        topic="  Example research  ",
        keywords=[" alpha ", "ALPHA", "beta"],
    )

    assert request.topic == "Example research"
    assert request.keywords == ["alpha", "beta"]


@pytest.mark.parametrize(
    "payload",
    [
        {"topic": "  "},
        {"topic": "ok", "keywords": [""]},
        {"topic": "valid topic", "keywords": ["x"] * 11},
        {"topic": "valid topic", "unknown": True},
    ],
)
def test_scout_request_rejects_invalid_input(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ScoutRunRequest.model_validate(payload)
