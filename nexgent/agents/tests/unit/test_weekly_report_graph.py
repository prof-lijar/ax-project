from collections.abc import Sequence
from typing import Any

import pytest
from ax_integrations import ChatMessage, ModelRequestError
from pydantic import ValidationError

from workflows.weekly_report import graph

VALID_NARRATIVE = (
    '{"summary":"업무 흐름을 안정적으로 이어가고 있습니다.",'
    '"suggestions":["우선순위를 꾸준히 점검하세요.",'
    '"방해 요인을 미리 정리하세요."]}'
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
        assert max_tokens == 600
        assert temperature == 0.1
        return VALID_NARRATIVE


class MixedFailureModel(FakeNarrativeModel):
    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> str:
        if "박준호" in messages[1]["content"]:
            raise ModelRequestError("synthetic model failure", retryable=False)
        return await super().complete(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )


class FixedResponseModel:
    def __init__(self, response: str | Exception) -> None:
        self.response = response

    async def complete(self, *args: Any, **kwargs: Any) -> str:
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.mark.asyncio
async def test_graph_fans_out_and_returns_ordered_korean_reports(
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
    assert [report["user_id"] for report in result["reports"]] == [
        "user-001",
        "user-002",
        "user-003",
    ]
    assert len({report["user_id"] for report in result["reports"]}) == 3
    assert all(report["generation_mode"] == "llm" for report in result["reports"])
    assert all("## 이번 주 요약" in report["markdown"] for report in result["reports"])
    assert result["warnings"] == []


@pytest.mark.asyncio
async def test_one_user_model_failure_uses_fallback_and_batch_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: MixedFailureModel(),
    )

    result = await graph.ainvoke(
        {"week_start": "2026-08-03"},
        config={"max_concurrency": 4},
    )

    modes = {
        report["user_id"]: report["generation_mode"] for report in result["reports"]
    }
    assert modes == {
        "user-001": "llm",
        "user-002": "template_fallback",
        "user-003": "llm",
    }
    assert result["warnings"] == [
        "user-002: model_narrative_unavailable; template fallback used"
    ]
    assert "자동 대체됨" in result["reports"][1]["markdown"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        "",
        "not-json",
        '{"summary":"완료율이 90퍼센트입니다.","suggestions":["흐름을 유지하세요.","방해 요인을 정리하세요."]}',
        ModelRequestError("synthetic failure", retryable=False),
    ],
)
async def test_invalid_or_failed_model_output_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    response: str | Exception,
) -> None:
    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: FixedResponseModel(response),
    )

    result = await graph.ainvoke(
        {"week_start": "2026-08-03"},
        config={"max_concurrency": 4},
    )

    assert all(
        report["generation_mode"] == "template_fallback" for report in result["reports"]
    )
    assert len(result["warnings"]) == 3


@pytest.mark.asyncio
async def test_progress_events_are_bounded_and_do_not_expose_activity_records(
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
    assert sum(event["event"] == "user_report_ready" for event in custom) == 3
    assert custom[-1] == {
        "event": "batch_completed",
        "report_count": 3,
        "fallback_count": 0,
    }
    serialized = repr(custom)
    assert "records" not in serialized
    assert "display_name" not in serialized
    assert "provider" not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"week_start": "2026-08-04"}, "Monday"),
        ({"week_start": "2026-08-03", "timezone": "Invalid/Zone"}, "IANA"),
    ],
)
async def test_graph_rejects_invalid_requests(
    payload: dict[str, str], match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        await graph.ainvoke(payload)
