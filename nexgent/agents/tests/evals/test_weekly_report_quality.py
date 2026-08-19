from copy import deepcopy

import pytest
from ax_contracts import WardWeeklyReportBatchResult
from ax_evals import evaluate_weekly_report_batch, weekly_report_release_ready

from tests.unit.test_weekly_report_graph import VALID_NARRATIVE
from workflows.weekly_report import graph
from workflows.weekly_report.tools.source_repository import (
    MockWeeklyReportSourceRepository,
)


@pytest.fixture(autouse=True)
def use_deterministic_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_weekly_report_source_repository",
        lambda: MockWeeklyReportSourceRepository(),
    )


@pytest.mark.asyncio
async def test_weekly_report_meets_deterministic_release_criteria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EvaluatedModel:
        async def complete(self, *args: object, **kwargs: object) -> str:
            return VALID_NARRATIVE

    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: EvaluatedModel(),
    )
    output = await graph.ainvoke({"week_start": "2026-08-03"})
    evaluations = evaluate_weekly_report_batch(
        WardWeeklyReportBatchResult.model_validate(output)
    )
    assert {evaluation.criterion for evaluation in evaluations} == {
        "batch_completeness",
        "korean_markdown_structure",
        "personalization",
        "numeric_grounding",
        "narrative_safety",
        "fallback_disclosure",
    }
    assert weekly_report_release_ready(evaluations)


@pytest.mark.asyncio
async def test_tampered_metric_prevents_release(monkeypatch: pytest.MonkeyPatch) -> None:
    class EvaluatedModel:
        async def complete(self, *args: object, **kwargs: object) -> str:
            return VALID_NARRATIVE

    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: EvaluatedModel(),
    )
    output = await graph.ainvoke({"week_start": "2026-08-03"})
    tampered = deepcopy(output)
    metrics = tampered["reports"][0]["metrics"]
    expected = (
        f"| 위험 감지일 | {metrics['current']['danger_days']}일 | "
        f"{metrics['previous']['danger_days']}일 | {metrics['delta']['danger_days']:+d}일 |"
    )
    tampered["reports"][0]["markdown"] = tampered["reports"][0]["markdown"].replace(
        expected, "| 위험 감지일 | 7일 | 7일 | +0일 |", 1
    )
    evaluations = evaluate_weekly_report_batch(
        WardWeeklyReportBatchResult.model_validate(tampered)
    )
    grounding = next(item for item in evaluations if item.criterion == "numeric_grounding")
    assert grounding.status == "failed"
    assert not weekly_report_release_ready(evaluations)
