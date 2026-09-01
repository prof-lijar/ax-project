from datetime import date

import pytest
from ax_contracts import WardWeeklyMetrics

from workflows.weekly_report.agents.reporter.fallback import build_fallback
from workflows.weekly_report.agents.reporter.narrative import generate_narrative
from workflows.weekly_report.agents.reporter.policy import validate_summary_text
from workflows.weekly_report.agents.reporter.prompt import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_messages,
)
from workflows.weekly_report.domain.derived_metrics import build_fact_package
from workflows.weekly_report.tools.source_repository import _mock_delta, _snapshot


def _metrics(
    *,
    display_name: str = "대상",
    current_updates: dict[str, int | float | None] | None = None,
    previous_updates: dict[str, int | float | None] | None = None,
) -> WardWeeklyMetrics:
    current = _snapshot(101, current=True).model_copy(update=current_updates or {})
    previous = _snapshot(101, current=False).model_copy(update=previous_updates or {})
    return WardWeeklyMetrics(
        ward_id=101,
        display_name=display_name,
        week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10),
        current=current,
        previous=previous,
        delta=_mock_delta(current, previous),
    )


def _desired_facts():
    return build_fact_package(
        _metrics(
            display_name="[넥스터] 이경주",
            current_updates={
                "movement_count_total": 60,
                "remote_control_count_total": 200,
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_humidity_days": 4,
                "risk_detected_count": 0,
            },
            previous_updates={
                "movement_count_total": 100,
                "remote_control_count_total": 100,
            },
        )
    )


def test_fact_package_supplies_section_results_without_formula_summary() -> None:
    facts = _desired_facts()

    assert facts.weekly_report_data is not None
    assert facts.weekly_report_data.subscriber == "[넥스터] 이경주"
    assert facts.weekly_report_data.living_activity.summary == "조금 감소"
    assert facts.weekly_report_data.living_pattern.summary == "조금 증가"
    assert facts.weekly_report_data.indoor_environment.summary == "습한 날 이어짐"
    assert "활동" in facts.required_topics
    assert "실내 환경" in facts.required_topics


def test_prompt_uses_requested_system_instructions_and_report_data_only() -> None:
    messages = build_messages(_desired_facts())

    assert PROMPT_VERSION == "weekly-korean-free-summary-v21"
    assert len(messages) == 1
    system = messages[0]["content"]
    assert SYSTEM_PROMPT.startswith("당신은 고령자 생활 모니터링 서비스의")
    assert "보호자가 한 번에 이해할 수 있는 짧은 한 문단" in system
    assert "숫자, 점수, 날짜, 횟수, 비율" in system
    assert "총평 본문만 출력합니다" in system
    assert '"가입자": "[넥스터] 이경주"' in system
    assert '"생활 활동"' in system
    assert '"생활 패턴"' in system
    assert '"실내 환경"' in system
    assert '"기기 상태"' in system
    assert "summary_outline" not in system
    assert "required_topics" not in system
    assert "{{WEEKLY_REPORT_DATA}}" not in system


@pytest.mark.asyncio
async def test_llm_authors_the_complete_weekly_summary_without_formula_copy() -> None:
    facts = _desired_facts()
    desired = (
        "지난 한 주 [넥스터] 이경주님은 전반적으로 평소와 비슷한 생활 흐름을 이어가셨어요. "
        "생활 활동은 다소 줄었지만, TV 이용 등 일상적인 생활 패턴은 조금 늘어난 모습이었어요. "
        "생활 정보는 빠짐없이 잘 들어왔고, 습한 날이 여러 번 이어졌어요. "
        "집 안이 너무 습하지 않도록 제습이나 환기가 잘 되고 있는지도 한 번 살펴봐 주세요."
    )

    class Model:
        async def complete(self, *args: object, **kwargs: object) -> str:
            return desired

    narrative, mode, metadata = await generate_narrative(Model(), facts)

    assert mode == "llm"
    assert metadata.prompt_version == "weekly-korean-free-summary-v21"
    assert f"{narrative.headline} {narrative.analysis_text}" == desired
    assert narrative.observations == []
    assert narrative.suggestions == []


@pytest.mark.parametrize(
    "invalid",
    [
        "지난 한 주 활동이 20퍼센트 줄었어요.",
        "지난 한 주 움직임이 줄었어요.",
        "지난 한 주 리모컨 사용이 늘었어요.",
        "지난 한 주 상태는 GOOD이에요.",
        "# 총평\n지난 한 주 생활을 살펴봤어요.",
        "지난 한 주 생활 흐름을 확인했습니다.",
    ],
)
def test_summary_validation_rejects_forbidden_output(invalid: str) -> None:
    with pytest.raises(ValueError):
        validate_summary_text(invalid, _desired_facts())


@pytest.mark.asyncio
async def test_invalid_summary_gets_one_specific_correction_retry() -> None:
    facts = _desired_facts()
    corrected = (
        "지난 한 주 [넥스터] 이경주님은 평소와 비슷한 흐름을 이어가셨어요. "
        "생활 활동은 다소 줄고 TV 이용 등 일상적인 생활 패턴은 조금 늘었어요. "
        "습한 날이 이어져 환기가 잘 되고 있는지 살펴봐 주세요."
    )

    class Model:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, messages, **kwargs: object) -> str:
            self.calls += 1
            if self.calls == 1:
                return "지난 한 주 움직임이 줄고 리모컨 사용은 늘었어요."
            assert "제거하거나 자연스러운 생활 언어로" in messages[-1]["content"]
            return corrected

    model = Model()
    narrative, mode, _ = await generate_narrative(model, facts)

    assert model.calls == 2
    assert mode == "llm"
    assert f"{narrative.headline} {narrative.analysis_text}" == corrected


def test_fallback_is_one_compliant_paragraph_when_model_is_unavailable() -> None:
    facts = _desired_facts()
    narrative = build_fallback(facts)
    summary = f"{narrative.headline} {narrative.analysis_text}"

    assert validate_summary_text(summary, facts) == summary
    assert not any(character.isdigit() for character in summary)
    assert "움직임" not in summary
    assert "리모컨" not in summary
    assert "GOOD" not in summary
    assert "CAUTION" not in summary
    assert "RISK" not in summary
