from copy import deepcopy

import pytest
from ax_contracts import WardWeeklyReportBatchResult
from ax_evals import evaluate_weekly_report_batch, weekly_report_release_ready

from workflows.weekly_report import graph
from workflows.weekly_report.repository import MockWeeklyWardRiskRepository


@pytest.fixture(autouse=True)
def use_deterministic_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_weekly_ward_risk_repository",
        lambda: MockWeeklyWardRiskRepository(),
    )


@pytest.mark.asyncio
async def test_weekly_report_meets_all_deterministic_release_criteria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EvaluatedModel:
        async def complete(self, *args: object, **kwargs: object) -> str:
            return (
                '{"summary":"검증된 위험 감지 흐름을 바탕으로 최근 상태를 확인해야 합니다.",'
                '"suggestions":["최근 감지 기록을 확인하세요.",'
                '"후속 점검 기록을 정리하세요."]}'
            )

    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: EvaluatedModel(),
    )
    output = await graph.ainvoke(
        {"week_start": "2026-08-03"}, config={"max_concurrency": 4}
    )
    result = WardWeeklyReportBatchResult.model_validate(output)

    evaluations = evaluate_weekly_report_batch(result)

    assert {evaluation.criterion for evaluation in evaluations} == {
        "batch_completeness",
        "korean_markdown_structure",
        "personalization",
        "numeric_grounding",
        "fallback_disclosure",
    }
    assert weekly_report_release_ready(evaluations)


@pytest.mark.asyncio
async def test_tampered_metric_prevents_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FallbackModel:
        async def complete(self, *args: object, **kwargs: object) -> str:
            raise ValueError("force deterministic fallback")

    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: FallbackModel(),
    )
    output = await graph.ainvoke(
        {"week_start": "2026-08-03"}, config={"max_concurrency": 4}
    )
    tampered = deepcopy(output)
    tampered["reports"][0]["markdown"] = tampered["reports"][0][
        "markdown"
    ].replace("| 위험 감지일 | 2일", "| 위험 감지일 | 7일", 1)
    result = WardWeeklyReportBatchResult.model_validate(tampered)

    evaluations = evaluate_weekly_report_batch(result)

    grounding = next(
        evaluation
        for evaluation in evaluations
        if evaluation.criterion == "numeric_grounding"
    )
    assert grounding.status == "failed"
    assert not weekly_report_release_ready(evaluations)
