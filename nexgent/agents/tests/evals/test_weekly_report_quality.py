from copy import deepcopy

import pytest
from ax_contracts import WeeklyReportBatchResult
from ax_evals import evaluate_weekly_report_batch, weekly_report_release_ready

from workflows.weekly_report import graph


@pytest.mark.asyncio
async def test_weekly_report_meets_all_deterministic_release_criteria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EvaluatedModel:
        async def complete(self, *args: object, **kwargs: object) -> str:
            return (
                '{"summary":"검증된 업무 흐름을 바탕으로 안정적인 진전이 확인됩니다.",'
                '"suggestions":["우선순위를 꾸준히 점검하세요.",'
                '"방해 요인을 미리 정리하세요."]}'
            )

    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: EvaluatedModel(),
    )
    output = await graph.ainvoke(
        {"week_start": "2026-08-03"},
        config={"max_concurrency": 4},
    )
    result = WeeklyReportBatchResult.model_validate(output)

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
        {"week_start": "2026-08-03"},
        config={"max_concurrency": 4},
    )
    tampered = deepcopy(output)
    tampered["reports"][0]["markdown"] = tampered["reports"][0]["markdown"].replace(
        "| 배정 업무 | 10건",
        "| 배정 업무 | 999건",
        1,
    )
    result = WeeklyReportBatchResult.model_validate(tampered)

    evaluations = evaluate_weekly_report_batch(result)

    grounding = next(
        evaluation
        for evaluation in evaluations
        if evaluation.criterion == "numeric_grounding"
    )
    assert grounding.status == "failed"
    assert not weekly_report_release_ready(evaluations)
