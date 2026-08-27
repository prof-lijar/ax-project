from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import SearchPlan


@pytest.mark.parametrize(
    "queries",
    [
        ["고독사 예방 AI IoT 서비스"],
        ["AI 돌봄 독거노인 모니터링", "IoT 고독사 예방 최근 동향"],
        ["one", "two", "three"],
    ],
)
def test_search_plan_accepts_one_to_three_concise_queries(queries: list[str]) -> None:
    plan = SearchPlan(queries=queries)

    assert plan.queries == queries


@pytest.mark.parametrize(
    "queries",
    [
        [],
        ["   "],
        ["one", "two", "three", "four"],
        ["https://example.com/search"],
        ["x" * 161],
    ],
)
def test_search_plan_rejects_invalid_queries(queries: list[str]) -> None:
    with pytest.raises(ValidationError):
        SearchPlan(queries=queries)


def test_search_plan_normalizes_and_deduplicates_queries() -> None:
    plan = SearchPlan(queries=["  AI 돌봄  ", "ai 돌봄", "IoT 모니터링"])

    assert plan.queries == ["AI 돌봄", "IoT 모니터링"]
