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


def _desired_facts(display_name: str = "[넥스터] 이경주"):
    return build_fact_package(
        _metrics(
            display_name=display_name,
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

    assert PROMPT_VERSION == "weekly-korean-free-summary-v28"
    assert len(messages) == 1
    system = messages[0]["content"]
    assert SYSTEM_PROMPT.startswith("당신은 고령자 생활 모니터링 서비스의")
    assert "보호자가 한 번에 이해할 수 있는 짧은 한 문단" in system
    assert "숫자, 점수, 날짜, 횟수, 비율" in system
    assert "총평 본문만 출력합니다" in system
    assert "같은 목적의 행동 제안은 한 번만" in system
    assert "위험 관리 및 별도 확인 기록은 한주 총평의 작성 대상이 아닙니다" in system
    assert "혼자 사시는 부모님의 생활을 직접 확인하기 어려운 자녀 보호자" in system
    assert "짧은 문장을 연달아 나열하지 않습니다" in system
    assert "지금 당장 조치해야 하는 느낌" in system
    assert "문단의 마지막 한 문장에서만" in system
    assert "다정하게" in system
    assert "님은” 바로 뒤에서 “활동은" in system
    assert '"총평 대상 이름": "[넥스터] 이경주"' in system
    assert '"생활 활동"' in system
    assert '"생활 패턴"' in system
    assert '"실내 환경"' in system
    assert '"기기 상태"' in system
    assert '"위험 관리"' not in system.split("<가입자_주간_데이터>", 1)[1]
    assert '"기본 정보"' not in system
    assert '"전체 상태"' not in system
    assert '"가입자 상태 점수"' not in system
    assert '"주차"' not in system
    assert '"기간"' not in system
    assert "summary_outline" not in system
    assert "required_topics" not in system
    assert "{{WEEKLY_REPORT_DATA}}" not in system


@pytest.mark.asyncio
async def test_llm_authors_the_complete_weekly_summary_without_formula_copy() -> None:
    facts = _desired_facts()
    desired = (
        "지난 한 주 [넥스터] 이경주님은 활동이 다소 줄었지만, TV 이용 등 일상적인 생활 패턴은 조금 늘어난 모습이었어요. "
        "생활 정보는 빠짐없이 잘 들어왔고, 습한 날이 여러 번 이어졌어요. "
        "집 안이 너무 습하지 않도록 제습이나 환기가 잘 되고 있는지도 한 번 살펴봐 주세요."
    )

    class Model:
        async def complete(self, *args: object, **kwargs: object) -> str:
            return desired

    narrative, mode, metadata = await generate_narrative(Model(), facts)

    assert mode == "llm"
    assert metadata.prompt_version == "weekly-korean-free-summary-v28"
    assert f"{narrative.headline} {narrative.analysis_text}" == desired
    assert narrative.observations == []
    assert narrative.suggestions == []


@pytest.mark.parametrize(
    "invalid",
    [
        "지난 한 주 활동이 20퍼센트 줄었어요.",
        "지난 한 주 움직임이 줄었어요.",
        "지난 한 주 리모컨 사용이 늘었어요.",
        "지난 한 주 위험한 모습이 확인됐어요.",
        "지난 한 주 상태는 GOOD이에요.",
        "# 총평\n지난 한 주 생활을 살펴봤어요.",
        "지난 한 주 생활 흐름을 확인했습니다.",
    ],
)
def test_summary_validation_rejects_forbidden_output(invalid: str) -> None:
    with pytest.raises(ValueError):
        validate_summary_text(invalid, _desired_facts())


def test_summary_validation_rejects_repeated_findings_and_actions() -> None:
    repeated = (
        "지난 한 주 홍영준님은 평소와 조금 다른 생활 모습이 보여요. "
        "활동이 많이 줄었어요. 안부를 한 번 확인해 주세요. "
        "TV 이용 등 일상적인 생활 패턴이 많이 줄었어요. "
        "안부를 한 번 확인해 주세요. "
        "일부 생활 정보가 평소보다 적게 들어온 날이 있었어요. "
        "습한 날이 여러 번 이어졌어요."
    )

    with pytest.raises(ValueError, match="choppy section recital"):
        validate_summary_text(repeated, _desired_facts())


@pytest.mark.parametrize(
    "reassurance",
    [
        "다행히 안전한 상태였지만 기기 전원을 확인해 주세요.",
        "안전한 상태여서 안심해도 괜찮아요.",
        "기기 정보가 들어오지 않았지만 문제없어요.",
    ],
)
def test_summary_validation_rejects_unsupported_safety_reassurance(
    reassurance: str,
) -> None:
    with pytest.raises(ValueError, match="unsupported safety reassurance"):
        validate_summary_text(f"지난 한 주 대상님은 {reassurance}", _desired_facts())


def test_summary_validation_excludes_risk_management_even_when_record_exists() -> None:
    facts = build_fact_package(
        _metrics(
            current_updates={"risk_detected_count": 1},
            previous_updates={"movement_count_total": 168},
        )
    )
    summary = (
        "지난 한 주 대상님은 활동과 TV 이용 등 일상적인 생활 패턴이 비슷하게 이어졌어요. "
        "생활 정보도 잘 들어왔고 집 안도 대체로 쾌적했어요. "
        "평소처럼 안부를 확인해 주세요."
    )
    excluded_record = (
        "지난 한 주 대상님은 활동과 TV 이용 등 일상적인 생활 패턴이 비슷하게 이어졌고 생활 흐름을 함께 살펴볼 필요가 있는 기록도 있었어요. "
        "생활 정보도 잘 들어왔고 집 안도 대체로 쾌적했어요. "
        "안부를 확인해 주세요."
    )

    assert validate_summary_text(summary, facts) == summary
    with pytest.raises(ValueError, match="excluded risk-management content"):
        validate_summary_text(excluded_record, facts)


def test_summary_validation_does_not_mention_an_absent_risk_record() -> None:
    summary = (
        "지난 한 주 [넥스터] 이경주님은 전반적으로 평소와 비슷한 생활 흐름을 이어가셨어요. "
        "생활 활동은 조금 줄었지만 TV 이용 등 일상적인 생활 패턴은 조금 늘었어요. "
        "생활 흐름을 함께 살펴볼 기록은 없었고 생활 정보는 빠짐없이 잘 들어왔어요. "
        "습한 날이 이어져 제습이나 환기 상태를 살펴봐 주세요."
    )

    with pytest.raises(ValueError, match="excluded risk-management content"):
        validate_summary_text(summary, _desired_facts())


@pytest.mark.parametrize(
    "alarming",
    [
        "지난 한 주 생활 흐름이 심각해 보여요.",
        "지난 한 주 생활 흐름을 즉시 확인해 주세요.",
        "지난 한 주 생활 흐름을 서둘러 확인해 주세요.",
        "지난 한 주 생활 흐름을 주의 깊게 살펴봐 주세요.",
        "지난 한 주 생활 모습이 크게 달라졌어요.",
        "지난 한 주 생활 흐름을 확인해 주세요!",
    ],
)
def test_summary_validation_rejects_alarming_or_rushed_wording(
    alarming: str,
) -> None:
    with pytest.raises(ValueError, match="alarming wording"):
        validate_summary_text(alarming, _desired_facts())


def test_prompt_omits_risk_management_when_a_record_exists() -> None:
    facts = build_fact_package(
        _metrics(current_updates={"risk_detected_count": 1})
    )
    system = build_messages(facts)[0]["content"]
    payload = system.split("<가입자_주간_데이터>", 1)[1].split(
        "</가입자_주간_데이터>", 1
    )[0]

    assert '"별도 확인 기록"' not in payload
    assert '"위험 관리"' not in payload
    assert "살펴볼 기록" not in payload
    assert "위험" not in payload


@pytest.mark.parametrize(
    "wording",
    [
        "홍영준님의 안부를 다정하게 확인해 주세요.",
        "홍영준님의 안부를 따뜻하게 확인해 주세요.",
        "TV 이용 시간이 평소보다 줄었어요.",
        "활동량이 평소보다 줄었어요.",
    ],
)
def test_summary_validation_rejects_persona_misaligned_wording(
    wording: str,
) -> None:
    summary = (
        "지난 한 주 홍영준님은 활동과 TV 이용 등 일상적인 생활 패턴이 조금 달랐어요. "
        "생활 정보는 잘 들어왔고 집 안은 대체로 쾌적했어요. "
        f"{wording}"
    )

    with pytest.raises(ValueError, match="persona-misaligned wording"):
        validate_summary_text(summary, _desired_facts("홍영준"))


def test_summary_validation_requires_one_final_guardian_action() -> None:
    facts = _desired_facts("홍영준")
    facts_after_action = (
        "지난 한 주 홍영준님은 활동이 조금 줄고 TV 이용 등 일상적인 생활 패턴은 조금 늘었어요. "
        "습한 날이 여러 번 이어져 제습이나 환기 상태를 살펴봐 주세요. "
        "생활 정보는 빠짐없이 잘 들어왔어요."
    )
    repeated_actions = (
        "지난 한 주 홍영준님은 활동이 조금 줄고 TV 이용 등 일상적인 생활 패턴은 조금 늘었어요. "
        "습한 날이 여러 번 이어져 제습이나 환기 상태를 살펴봐 주세요. "
        "홍영준님의 안부도 확인해 주세요."
    )

    with pytest.raises(ValueError, match="facts after the closing action"):
        validate_summary_text(facts_after_action, facts)
    with pytest.raises(ValueError, match="consolidate actions in the closing"):
        validate_summary_text(repeated_actions, facts)


def test_summary_validation_accepts_observations_then_practical_close() -> None:
    facts = _desired_facts("홍영준")
    summary = (
        "지난 한 주 홍영준님은 활동이 조금 줄고 TV 이용 등 일상적인 생활 패턴은 조금 늘었어요. "
        "생활 정보는 빠짐없이 잘 들어왔고 습한 날이 여러 번 이어졌어요. "
        "평소와 달라진 점은 없는지 홍영준님의 안부를 확인하고 제습이나 환기 상태도 함께 살펴봐 주세요."
    )

    assert validate_summary_text(summary, facts) == summary


def test_all_good_summary_joins_related_findings_instead_of_reciting_sections() -> None:
    facts = build_fact_package(
        _metrics(
            display_name="[넥스터]_김종환",
            current_updates={
                "movement_count_total": 100,
                "remote_control_count_total": 100,
                "risk_detected_count": 0,
            },
            previous_updates={
                "movement_count_total": 100,
                "remote_control_count_total": 100,
            },
        )
    )
    choppy = (
        "지난 한 주 [넥스터] 김종환님은 활동과 TV 이용 등 일상적인 생활 패턴이 비슷하게 이어졌어요. "
        "생활 정보가 빠짐없이 잘 들어왔어요. "
        "집 안 온도와 습도가 대체로 쾌적하게 유지됐어요. "
        "생활 흐름도 평소와 비슷했어요. "
        "평소처럼 안부를 확인해 주세요."
    )
    connected = (
        "지난 한 주 [넥스터] 김종환님은 활동과 TV 이용 등 일상적인 생활 패턴이 평소와 비슷하게 이어졌어요. "
        "생활 정보도 빠짐없이 잘 들어왔고, 집 안 온도와 습도도 대체로 쾌적하게 유지됐어요. "
        "평소처럼 안부를 확인해 주세요."
    )

    with pytest.raises(ValueError, match="choppy section recital"):
        validate_summary_text(choppy, facts)
    assert validate_summary_text(connected, facts) == connected


def test_summary_opening_avoids_consecutive_topic_particles() -> None:
    facts = _desired_facts("장덕순")
    awkward = (
        "지난 한 주 장덕순님은 활동은 조금 줄었지만 TV 이용 등 일상적인 생활 패턴은 조금 늘었어요. "
        "생활 정보는 빠짐없이 잘 들어왔고 습한 날이 여러 번 이어졌어요. "
        "장덕순님의 안부를 확인하면서 제습이나 환기 상태도 살펴봐 주세요."
    )
    natural = awkward.replace("장덕순님은 활동은", "장덕순님은 활동이")

    with pytest.raises(ValueError, match="repeats the topic particle"):
        validate_summary_text(awkward, facts)
    assert validate_summary_text(natural, facts) == natural


def test_no_reception_prompt_contains_only_the_grounded_two_sentence_case() -> None:
    facts = build_fact_package(
        _metrics(
            display_name="노월연",
            current_updates={
                "covered_days": 0,
                "daily_summary_count": 0,
                "device_good_count": None,
                "device_power_count": None,
                "device_position_count": None,
                "risk_detected_count": 0,
            },
        )
    )
    system = build_messages(facts)[0]["content"]
    payload = system.split("<가입자_주간_데이터>", 1)[1].split(
        "</가입자_주간_데이터>", 1
    )[0]

    assert '"총평 대상 이름": "노월연"' in payload
    assert '"전체 생활 정보 수신": "없음"' in payload
    assert "생활 정보가 들어오지 않은 날이 있었어요" in payload
    assert "기기 전원이 잘 연결되어 있는지 확인해 주세요" in payload
    assert '"전체 상태"' not in payload
    assert '"생활 활동"' not in payload
    assert '"실내 환경"' not in payload


def test_no_reception_summary_uses_only_the_requested_copy() -> None:
    facts = build_fact_package(
        _metrics(
            display_name="김면자",
            current_updates={
                "covered_days": 0,
                "daily_summary_count": 0,
                "device_good_count": None,
                "device_power_count": None,
                "device_position_count": None,
                "risk_detected_count": 0,
            },
        )
    )
    desired = (
        "지난 한 주 김면자님은 생활 정보가 들어오지 않은 날이 있었어요. "
        "기기 전원이 잘 연결되어 있는지 확인해 주세요."
    )
    generic_assessment = (
        "지난 한 주 김면자님의 생활 모습이 평소와 조금 다르게 보여요. "
        "기기 전원이 잘 연결되어 있는지 확인해 주세요."
    )

    assert validate_summary_text(desired, facts) == desired
    with pytest.raises(ValueError, match="no-reception two-sentence copy"):
        validate_summary_text(generic_assessment, facts)

    fallback = build_fallback(facts)
    assert f"{fallback.headline} {fallback.analysis_text}" == desired


def test_known_name_replaces_generic_subscriber_reference() -> None:
    facts = _desired_facts("홍영준")
    generic = (
        "지난 한 주 홍영준님은 생활 활동이 조금 줄었지만 TV 이용 등 일상적인 생활 패턴은 조금 늘었어요. "
        "생활 정보는 빠짐없이 잘 들어왔고 습한 날이 여러 번 이어졌어요. "
        "가입자님의 안부와 함께 제습이나 환기 상태를 살펴봐 주세요."
    )
    personalized = generic.replace("가입자님의", "홍영준님의")

    with pytest.raises(ValueError, match="generic subscriber reference"):
        validate_summary_text(generic, facts)
    assert validate_summary_text(personalized, facts) == personalized


def test_summary_name_normalizes_service_separator_only_in_summary() -> None:
    facts = _desired_facts("[넥스터]_김동현")
    payload = build_messages(facts)[0]["content"]
    summary = (
        "지난 한 주 [넥스터] 김동현님은 활동이 조금 줄었지만 TV 이용 등 일상적인 생활 패턴은 조금 늘었어요. "
        "생활 정보는 빠짐없이 잘 들어왔고 습한 날이 여러 번 이어졌어요. "
        "집 안이 너무 습하지 않도록 제습이나 환기 상태를 살펴봐 주세요."
    )

    assert '"총평 대상 이름": "[넥스터] 김동현"' in payload
    assert validate_summary_text(summary, facts) == summary
    assert facts.weekly_report_data is not None
    assert facts.weekly_report_data.subscriber == "[넥스터]_김동현"


def test_summary_validation_accepts_consolidated_attention_summary() -> None:
    facts = _desired_facts()
    summary = (
        "지난 한 주 [넥스터] 이경주님은 활동이 조금 줄었지만 TV 이용 등 일상적인 생활 패턴은 조금 늘었어요. "
        "생활 정보는 빠짐없이 잘 들어왔고 습한 날이 여러 번 이어졌어요. "
        "집 안이 너무 습하지 않도록 제습이나 환기 상태를 한 번 살펴봐 주세요."
    )

    assert validate_summary_text(summary, facts) == summary


@pytest.mark.asyncio
async def test_invalid_summary_gets_one_specific_correction_retry() -> None:
    facts = _desired_facts()
    corrected = (
        "지난 한 주 [넥스터] 이경주님은 활동이 다소 줄고 TV 이용 등 일상적인 생활 패턴은 조금 늘었어요. "
        "습한 날이 이어져 환기가 잘 되고 있는지 살펴봐 주세요."
    )

    class Model:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, messages, **kwargs: object) -> str:
            self.calls += 1
            if self.calls == 1:
                return "지난 한 주 움직임이 줄고 리모컨 사용은 늘었어요."
            assert "제거하거나 차분한 생활 언어로" in messages[-1]["content"]
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
    assert summary.count("안부") <= 1
