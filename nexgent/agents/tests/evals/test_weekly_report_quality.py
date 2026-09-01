from copy import deepcopy

import pytest
from ax_contracts import WardWeeklyReportBatchResult
from ax_evals import evaluate_weekly_report_batch, weekly_report_release_ready

from tests.unit.test_weekly_report_graph import valid_narrative_for_messages
from workflows.weekly_report import graph
from workflows.weekly_report.domain.rendering import render_report
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
        async def complete(self, messages, **kwargs: object) -> str:
            return valid_narrative_for_messages(messages)

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
        "device_reception_consistency",
        "narrative_safety",
        "fallback_disclosure",
    }
    assert weekly_report_release_ready(evaluations)


@pytest.mark.asyncio
async def test_tampered_metric_prevents_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EvaluatedModel:
        async def complete(self, messages, **kwargs: object) -> str:
            return valid_narrative_for_messages(messages)

    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: EvaluatedModel(),
    )
    output = await graph.ainvoke({"week_start": "2026-08-03"})
    tampered = deepcopy(output)
    metrics = tampered["reports"][0]["metrics"]
    expected = (
        f"  - 위험 감지: {metrics['current']['risk_detected_count']}회\n"
        f"  - 정상 해제: {metrics['current']['risk_resolved_count']}회\n"
        f"  - 2주 전: {metrics['previous']['risk_detected_count']}회 / "
        f"{metrics['previous']['risk_resolved_count']}회"
    )
    tampered["reports"][0]["markdown"] = tampered["reports"][0]["markdown"].replace(
        expected,
        "  - 위험 감지: 7회\n  - 정상 해제: 7회\n  - 2주 전: 7회 / 7회",
        1,
    )
    evaluations = evaluate_weekly_report_batch(
        WardWeeklyReportBatchResult.model_validate(tampered)
    )
    grounding = next(
        item for item in evaluations if item.criterion == "numeric_grounding"
    )
    assert grounding.status == "failed"
    assert not weekly_report_release_ready(evaluations)


@pytest.mark.asyncio
async def test_false_device_missing_data_copy_prevents_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EvaluatedModel:
        async def complete(self, messages, **kwargs: object) -> str:
            return valid_narrative_for_messages(messages)

    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: EvaluatedModel(),
    )
    output = await graph.ainvoke({"week_start": "2026-08-03"})
    tampered = deepcopy(output)
    markdown = tampered["reports"][0]["markdown"]
    markdown = markdown.replace(
        "## 기기 상태\n\n- 상태: GOOD",
        "## 기기 상태\n\n- 상태: 자료 없음",
        1,
    )
    tampered["reports"][0]["markdown"] = markdown.replace(
        "# 보호자 행동 제안",
        "# 보호자 행동 제안\n\n## 1. 기기 전원이 연결되어 있는지 확인해 주세요\n\n"
        "- 설명: 지난 한 주 기기 데이터 수신이 확인되지 않았어요.",
        1,
    )

    evaluations = evaluate_weekly_report_batch(
        WardWeeklyReportBatchResult.model_validate(tampered)
    )
    device = next(
        item for item in evaluations if item.criterion == "device_reception_consistency"
    )
    assert device.status == "failed"
    assert not weekly_report_release_ready(evaluations)


@pytest.mark.parametrize("night_awake_count", [None, 0.0])
@pytest.mark.asyncio
async def test_structure_evaluation_accepts_omitted_empty_sleep_section(
    monkeypatch: pytest.MonkeyPatch,
    night_awake_count: float | None,
) -> None:
    class EvaluatedModel:
        async def complete(self, messages, **kwargs: object) -> str:
            return valid_narrative_for_messages(messages)

    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_default_chat_model",
        lambda: EvaluatedModel(),
    )
    batch = WardWeeklyReportBatchResult.model_validate(
        await graph.ainvoke({"week_start": "2026-08-03"})
    )
    original = batch.reports[0]
    metrics = original.metrics.model_copy(
        update={
            "current": original.metrics.current.model_copy(
                update={
                    "sleep_time_avg": None,
                    "wake_up_time_avg": None,
                    "night_awake_count_avg": night_awake_count,
                }
            ),
            "previous": original.metrics.previous.model_copy(
                update={
                    "sleep_time_avg": None,
                    "wake_up_time_avg": None,
                    "night_awake_count_avg": night_awake_count,
                }
            ),
            "delta": original.metrics.delta.model_copy(
                update={
                    "sleep_time_minutes": None,
                    "wake_up_time_minutes": None,
                    "night_awake_count_avg": (
                        None if night_awake_count is None else 0.0
                    ),
                }
            ),
        }
    )
    report = render_report(
        metrics,
        original.narrative,
        original.generation_mode,
        original.generation,
    )
    batch = batch.model_copy(update={"reports": [report, *batch.reports[1:]]})

    evaluations = evaluate_weekly_report_batch(batch)
    structure = next(
        item for item in evaluations if item.criterion == "korean_markdown_structure"
    )
    assert structure.status == "passed"
    assert "수면 패턴" not in report.markdown
    assert "## 생활 활동" in report.markdown
    assert "## 생활 패턴" in report.markdown
