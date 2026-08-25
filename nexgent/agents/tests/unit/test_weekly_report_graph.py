import json
from collections.abc import Sequence
from typing import Any

import pytest
from ax_contracts import WeeklyReportSourceResponse
from ax_integrations import ChatMessage, ModelRequestError
from pydantic import ValidationError

from workflows.weekly_report import graph
from workflows.weekly_report.tools.source_repository import (
    MockWeeklyReportSourceRepository,
)

ANALYSIS = (
    "이번 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
    "확인된 자료에서는 지난주와 다른 부분도 있었지만, 측정된 변화만으로 이유를 단정하지 않았어요. "
    "활동과 휴식 흐름, 실내 온도와 습도 상태는 평소 모습과 함께 살펴보면 더 자연스럽게 이해할 수 있어요. "
    "자료가 충분한 부분은 나란히 비교했고 부족한 부분은 해석을 넓히지 않았어요. "
    "크게 서두르기보다 최근 안부와 생활 리듬을 편안하게 확인해 보시면 다음 흐름을 살피는 데 도움이 될 수 있어요."
)
VALID_NARRATIVE = json.dumps(
    {
        "headline": "이번 주 생활 흐름을 차분히 살펴봤어요.",
        "analysis_text": ANALYSIS,
        "observations": ["생활 흐름에 일부 변화가 보였어요."],
        "suggestions": ["최근 안부를 편안하게 확인해 보셔도 좋아요."],
    },
    ensure_ascii=False,
)


@pytest.fixture(autouse=True)
def use_deterministic_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_weekly_report_source_repository",
        lambda: MockWeeklyReportSourceRepository(),
    )


class FakeNarrativeModel:
    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> str:
        assert messages[0]["role"] == "system"
        assert "숫자를 쓰지 마세요" in messages[0]["content"]
        assert max_tokens == 900
        assert temperature == 0.2
        return VALID_NARRATIVE


class FixedResponseModel:
    def __init__(self, response: str | Exception) -> None:
        self.response = response

    async def complete(self, *args: Any, **kwargs: Any) -> str:
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.mark.asyncio
async def test_graph_returns_ordered_grounded_warm_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: FakeNarrativeModel(),
    )
    result = await graph.ainvoke(
        {"week_start": "2026-08-03", "timezone": "Asia/Seoul"},
        config={"max_concurrency": 4},
    )

    assert result["status"] == "completed"
    assert [report["ward_id"] for report in result["reports"]] == [101, 102, 103]
    assert all(report["generation_mode"] == "llm" for report in result["reports"])
    assert all(
        report["markdown"].startswith("# 주간 생활 리포트")
        for report in result["reports"]
    )
    assert all("## 5. 위험 관리" in report["markdown"] for report in result["reports"])
    assert all(report["narrative"]["analysis_text"] == ANALYSIS for report in result["reports"])


@pytest.mark.asyncio
async def test_graph_writes_the_requested_number_of_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: FakeNarrativeModel(),
    )

    result = await graph.ainvoke(
        {"week_start": "2026-08-03", "timezone": "Asia/Seoul", "limit": 2},
        config={"max_concurrency": 4},
    )

    assert [report["ward_id"] for report in result["reports"]] == [101, 102]


@pytest.mark.asyncio
async def test_failed_model_retries_then_uses_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: FixedResponseModel(ModelRequestError("synthetic", retryable=False)),
    )
    result = await graph.ainvoke(
        {"week_start": "2026-08-03"}, config={"max_concurrency": 4}
    )

    assert all(
        report["generation_mode"] == "template_fallback" for report in result["reports"]
    )
    assert all("자동 대체됨" in report["markdown"] for report in result["reports"])
    assert len(result["warnings"]) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        "",
        "not-json",
        json.dumps(
            {
                "headline": "위험합니다.",
                "analysis_text": ANALYSIS,
                "observations": ["기록을 확인했어요."],
                "suggestions": [],
            },
            ensure_ascii=False,
        ),
    ],
)
async def test_invalid_model_output_falls_back(
    monkeypatch: pytest.MonkeyPatch, response: str
) -> None:
    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: FixedResponseModel(response),
    )
    result = await graph.ainvoke({"week_start": "2026-08-03"})
    assert all(
        report["generation_mode"] == "template_fallback" for report in result["reports"]
    )


@pytest.mark.asyncio
async def test_progress_events_do_not_expose_source_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: FakeNarrativeModel(),
    )
    events = [
        event
        async for event in graph.astream(
            {"week_start": "2026-08-03"},
            config={"max_concurrency": 4},
            stream_mode=["custom", "values"],
            subgraphs=True,
        )
    ]
    custom = [data for _, mode, data in events if mode == "custom"]
    assert custom[0] == {"event": "batch_started", "week_start": "2026-08-03"}
    assert sum(event["event"] == "ward_report_ready" for event in custom) == 3
    assert custom[-1]["event"] == "batch_completed"
    assert "full_name" not in repr(custom)


@pytest.mark.asyncio
async def test_empty_candidate_page_completes_without_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EmptyRepository:
        async def load(self, request):
            return WeeklyReportSourceResponse(
                week_start=request.week_start,
                week_end=request.week_end,
                timezone=request.timezone,
                warnings=["no_candidate_wards"],
            )

    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_weekly_report_source_repository",
        lambda: EmptyRepository(),
    )
    result = await graph.ainvoke({"week_start": "2026-08-03"})
    assert result["reports"] == []
    assert result["warnings"] == ["no_candidate_wards"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"week_start": "2026-08-04"}, "Monday"),
        ({"week_start": "2026-08-03", "timezone": "Invalid/Zone"}, "IANA"),
        ({"week_start": "2026-08-03", "ward_ids": [1], "cursor": "x"}, "mutually"),
    ],
)
async def test_graph_rejects_invalid_requests(
    payload: dict[str, Any], match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        await graph.ainvoke(payload)


@pytest.mark.asyncio
async def test_graph_keeps_interactive_limit_bounded_to_twenty_five() -> None:
    with pytest.raises(ValueError, match="must not exceed 25"):
        await graph.ainvoke({"week_start": "2026-08-03", "limit": 100})
