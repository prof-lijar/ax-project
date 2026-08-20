import json
from datetime import date, timedelta

import pytest
from ax_contracts import WardWeeklyMetrics

from workflows.weekly_report.agents.reporter.fallback import build_fallback
from workflows.weekly_report.agents.reporter.narrative import generate_narrative
from workflows.weekly_report.agents.reporter.prompt import (
    PROMPT_VERSION,
    build_messages,
)
from workflows.weekly_report.domain.derived_metrics import build_fact_package
from workflows.weekly_report.domain.environment_policy import assess_environment
from workflows.weekly_report.tools.source_repository import _mock_delta, _snapshot


def _metrics(
    *,
    month: int,
    temperature_min: float,
    temperature_max: float,
    humidity_min: float = 40,
    humidity_max: float = 60,
) -> WardWeeklyMetrics:
    current = _snapshot(101, current=True).model_copy(
        update={
            "temperature_min": temperature_min,
            "temperature_max": temperature_max,
            "humidity_min": humidity_min,
            "humidity_max": humidity_max,
        }
    )
    previous = _snapshot(101, current=False)
    week_start = date(2026, month, 1)
    return WardWeeklyMetrics(
        ward_id=101,
        display_name="대상",
        week_start=week_start,
        week_end=week_start + timedelta(days=7),
        current=current,
        previous=previous,
        delta=_mock_delta(current, previous),
    )


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        (1, (18, 20)),
        (3, (18, 20)),
        (4, (20, 22)),
        (5, (20, 22)),
        (6, (26, 28)),
        (9, (26, 28)),
        (10, (20, 22)),
        (11, (18, 20)),
        (12, (18, 20)),
    ],
)
def test_temperature_policy_uses_reporting_week_start_month(
    month: int, expected: tuple[int, int]
) -> None:
    assessment = assess_environment(
        _metrics(
            month=month,
            temperature_min=expected[0],
            temperature_max=expected[1],
        )
    )

    assert (assessment.temperature_low, assessment.temperature_high) == expected
    assert assessment.temperature_status == "normal"
    assert assessment.humidity_status == "normal"


def test_environment_policy_classifies_weekly_extrema() -> None:
    assessment = assess_environment(
        _metrics(
            month=8,
            temperature_min=25,
            temperature_max=29,
            humidity_min=39,
            humidity_max=61,
        )
    )

    assert assessment.temperature_status == "variable"
    assert assessment.humidity_status == "variable"


def test_environment_policy_requires_both_extrema() -> None:
    assessment = assess_environment(
        _metrics(
            month=8,
            temperature_min=26,
            temperature_max=28,
        ).model_copy(
            update={
                "current": _snapshot(101, current=True).model_copy(
                    update={"temperature_min": None, "temperature_max": 28}
                )
            }
        )
    )

    assert assessment.temperature_status == "unavailable"


def test_environment_facts_are_required_in_weekly_analysis() -> None:
    facts = build_fact_package(
        _metrics(
            month=8,
            temperature_min=25,
            temperature_max=28,
            humidity_min=39,
            humidity_max=60,
        )
    )

    assert facts.required_topics == ["실내 환경"]
    assert any("추운 구간" in fact for fact in facts.facts)
    assert any("건조한 구간" in fact for fact in facts.facts)
    assert "온도" in build_fallback(facts).analysis_text

    messages = build_messages(facts)
    assert PROMPT_VERSION == "weekly-korean-warm-v3"
    assert "analysis_text에서 온도나 습도 상태를 반드시 언급하세요" in messages[0][
        "content"
    ]
    assert '"required_topics": ["실내 환경"]' in messages[1]["content"]


@pytest.mark.asyncio
async def test_reporter_rejects_analysis_that_omits_required_environment() -> None:
    facts = build_fact_package(
        _metrics(
            month=8,
            temperature_min=25,
            temperature_max=28,
        )
    )
    fallback = build_fallback(facts)
    environment_fact = next(fact for fact in facts.facts if "온도" in fact)
    missing_environment = fallback.model_copy(
        update={
            "analysis_text": fallback.analysis_text.replace(
                environment_fact,
                "이번 주 생활 흐름은 전반적으로 차분하게 이어졌습니다.",
                1,
            )
        }
    )

    class OmittingModel:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, *args: object, **kwargs: object) -> str:
            self.calls += 1
            return json.dumps(missing_environment.model_dump(), ensure_ascii=False)

    model = OmittingModel()
    narrative, mode, metadata = await generate_narrative(model, facts)

    assert model.calls == 2
    assert mode == "template_fallback"
    assert metadata.fallback_reason == "invalid_narrative_content"
    assert "온도" in narrative.analysis_text
