import json
from datetime import date, time

import pytest

from workflows.weekly_report.agents.reporter.fallback import build_fallback
from workflows.weekly_report.agents.reporter.narrative import generate_narrative
from workflows.weekly_report.domain.derived_metrics import build_fact_package
from workflows.weekly_report.domain.models import FactPackage
from workflows.weekly_report.source.calculator import calculate_metrics


def test_calculator_matches_weighted_and_linear_average_semantics() -> None:
    rows = [
        {
            "ward_id": 1,
            "device_id": 10,
            "date": date(2026, 8, 3),
            "temperature": 20,
            "temperature_count": 1,
            "humidity": 40,
            "humidity_count": 2,
            "light": 100,
            "light_count": 1,
            "min_temperature": 18,
            "max_temperature": 22,
            "min_humidity": 35,
            "max_humidity": 45,
            "min_light": 10,
            "max_light": 200,
            "light_on_time_minutes": 300,
            "movement_count": 10,
            "remote_control_count": 2,
            "wake_up_time": time(7),
            "sleep_time": time(22),
            "night_awake_count": 1,
        },
        {
            "ward_id": 1,
            "device_id": 10,
            "date": date(2026, 8, 4),
            "temperature": 30,
            "temperature_count": 3,
            "humidity": 50,
            "humidity_count": 2,
            "light": 200,
            "light_count": 1,
            "min_temperature": 25,
            "max_temperature": 32,
            "min_humidity": 45,
            "max_humidity": 55,
            "min_light": 20,
            "max_light": 300,
            "light_on_time_minutes": 500,
            "movement_count": 20,
            "remote_control_count": 4,
            "wake_up_time": time(9),
            "sleep_time": time(23),
            "night_awake_count": 3,
        },
    ]
    metrics = calculate_metrics(
        ward_names={1: "대상"},
        week_start=date(2026, 8, 3),
        daily_rows=rows,
        risk_rows=[
            {
                "ward_id": 1,
                "period_index": 1,
                "risk_detected_count": 2,
                "risk_resolved_count": 1,
                "risk_score_avg": 0.4,
                "danger_days": 1,
            }
        ],
        dispatch_rows=[],
    )[0]
    assert metrics.current.temperature_avg == 27.5
    assert metrics.current.movement_count_avg == 15
    assert metrics.current.wake_up_time_avg == time(8)
    assert metrics.current.covered_days == 2
    assert metrics.current.risk_detected_count == 2


def test_fact_package_prioritizes_data_dispatch_and_risk() -> None:
    from workflows.weekly_report.tools.source_repository import _mock_delta, _snapshot

    current = _snapshot(103, current=True).model_copy(update={"covered_days": 4})
    previous = _snapshot(103, current=False)
    from ax_contracts import WardWeeklyMetrics

    metrics = WardWeeklyMetrics(
        ward_id=103,
        display_name="대상",
        week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10),
        current=current,
        previous=previous,
        delta=_mock_delta(current, previous),
    )
    facts = build_fact_package(metrics)
    assert facts.coverage == "incomplete"
    assert facts.allowed_topics[:3] == ["자료 상태", "출동 요청", "위험 감지"]
    assert len(facts.suggested_actions) <= 3


@pytest.mark.asyncio
async def test_reporter_accepts_one_complete_json_code_fence() -> None:
    facts = FactPackage(
        coverage="complete",
        facts=["활동 흐름은 지난주와 비슷하게 이어졌습니다."],
        allowed_topics=["활동"],
        suggested_actions=[],
    )
    expected = build_fallback(facts)

    class FencedJsonModel:
        async def complete(self, *args: object, **kwargs: object) -> str:
            payload = json.dumps(expected.model_dump(mode="json"), ensure_ascii=False)
            return f"```json\n{payload}\n```"

    narrative, mode, metadata = await generate_narrative(FencedJsonModel(), facts)

    assert narrative == expected
    assert mode == "llm"
    assert metadata.validation_status == "passed"
    assert metadata.fallback_reason is None


@pytest.mark.asyncio
async def test_reporter_gives_specific_sentence_feedback_before_retry() -> None:
    facts = FactPackage(
        coverage="complete",
        facts=["활동 흐름은 지난주와 비슷하게 이어졌습니다."],
        allowed_topics=["활동"],
        suggested_actions=[],
    )
    expected = build_fallback(facts)
    too_few_sentences = expected.model_copy(
        update={"analysis_text": expected.analysis_text.replace(". ", ", ")}
    )

    class CorrectingModel:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, messages: list[dict[str, str]], **kwargs: object) -> str:
            self.calls += 1
            if self.calls == 1:
                value = too_few_sentences
            else:
                assert "마침표로 구분된 네 문장부터 여섯 문장" in messages[-1]["content"]
                value = expected
            return json.dumps(value.model_dump(mode="json"), ensure_ascii=False)

    model = CorrectingModel()
    narrative, mode, metadata = await generate_narrative(model, facts)

    assert model.calls == 2
    assert narrative == expected
    assert mode == "llm"
    assert metadata.validation_status == "passed"


@pytest.mark.asyncio
async def test_reporter_rejects_unsupported_topic_then_uses_fallback() -> None:
    facts = FactPackage(
        coverage="complete",
        facts=["활동 흐름은 지난주와 비슷하게 이어졌습니다."],
        allowed_topics=["활동"],
        suggested_actions=[],
    )
    unsupported = build_fallback(facts).model_copy(
        update={
            "analysis_text": build_fallback(facts).analysis_text.replace(
                "이번 주 생활 흐름", "이번 주 출동 요청과 생활 흐름", 1
            )
        }
    )

    class UnsupportedModel:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, *args: object, **kwargs: object) -> str:
            self.calls += 1
            return json.dumps(unsupported.model_dump(mode="json"), ensure_ascii=False)

    model = UnsupportedModel()
    narrative, mode, metadata = await generate_narrative(model, facts)
    assert model.calls == 2
    assert mode == "template_fallback"
    assert metadata.fallback_reason == "invalid_narrative_content"
    assert "출동" not in narrative.analysis_text
