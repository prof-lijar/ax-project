from datetime import date

from ax_contracts import WardWeeklyMetrics

from workflows.weekly_report.domain.derived_metrics import build_fact_package
from workflows.weekly_report.domain.device_reception_policy import (
    assess_device_reception,
    device_reception_description,
    device_reception_status_label,
    device_reception_summary,
)
from workflows.weekly_report.tools.source_repository import _mock_delta, _snapshot


def test_device_reception_good_uses_exact_approved_copy() -> None:
    assessment = assess_device_reception(_snapshot(101, current=True))

    assert assessment.status == "GOOD"
    assert assessment.kind == "device_good"
    assert device_reception_status_label(assessment) == "GOOD"
    assert device_reception_description(assessment) == (
        "모든 데이터가 정상적으로 수집되었어요."
    )
    assert device_reception_summary(assessment) == "수신상태 양호"


def test_device_power_has_precedence_and_uses_exact_approved_copy() -> None:
    snapshot = _snapshot(101, current=True).model_copy(
        update={
            "device_good_count": 3,
            "device_power_count": 2,
            "device_position_count": 2,
        }
    )

    assessment = assess_device_reception(snapshot)

    assert assessment.status == "CAUTION"
    assert assessment.kind == "device_power"
    assert device_reception_description(assessment) == (
        "기기 전원이 연결되어 있는지 확인해 주세요."
    )
    assert device_reception_summary(assessment) == "전원 확인 필요"


def test_device_position_uses_exact_approved_copy() -> None:
    snapshot = _snapshot(101, current=True).model_copy(
        update={
            "device_good_count": 5,
            "device_power_count": 0,
            "device_position_count": 2,
        }
    )

    assessment = assess_device_reception(snapshot)

    assert assessment.status == "CAUTION"
    assert assessment.kind == "device_position"
    assert device_reception_description(assessment) == (
        "움직임·리모컨 사용이 적게 확인됐어요. 기기 위치가 올바른지 확인해 주세요."
    )
    assert device_reception_summary(assessment) == "기기 위치 확인 필요"


def test_any_good_reception_is_good_when_no_caution_rule_matches() -> None:
    snapshot = _snapshot(101, current=True).model_copy(
        update={
            "device_good_count": 6,
            "device_power_count": 0,
            "device_position_count": 0,
        }
    )

    assessment = assess_device_reception(snapshot)

    assert assessment.status == "GOOD"
    assert assessment.kind == "device_good"
    assert assessment.other_count == 1
    assert device_reception_status_label(assessment) == "GOOD"
    assert device_reception_description(assessment) == (
        "모든 데이터가 정상적으로 수집되었어요."
    )
    assert device_reception_summary(assessment) == "수신상태 양호"


def test_zero_source_rows_request_a_device_power_check() -> None:
    snapshot = _snapshot(101, current=True).model_copy(
        update={
            "covered_days": 0,
            "daily_summary_count": 0,
            "device_count": 0,
            "device_good_count": None,
            "device_power_count": None,
            "device_position_count": None,
        }
    )

    assessment = assess_device_reception(snapshot)

    assert assessment.status == "UNAVAILABLE"
    assert assessment.kind == "device_no_data"
    assert assessment.other_count is None
    assert device_reception_status_label(assessment) == "자료 없음"
    assert device_reception_description(assessment) == (
        "기기 전원이 연결되어 있는지 확인해 주세요."
    )
    assert device_reception_summary(assessment) == "수신상태 확인 필요"


def test_rows_without_any_weekly_match_are_not_called_missing_or_power_loss() -> None:
    snapshot = _snapshot(101, current=True).model_copy(
        update={
            "device_good_count": 0,
            "device_power_count": 1,
            "device_position_count": 1,
        }
    )

    assessment = assess_device_reception(snapshot)

    assert assessment.status == "UNAVAILABLE"
    assert assessment.kind == "unavailable"
    assert assessment.other_count == 5
    assert device_reception_status_label(assessment) == "판정 불가"
    assert "자료가 충분하지" in device_reception_description(assessment)


def test_device_reception_fact_package_includes_significant_power_count() -> None:
    previous = _snapshot(101, current=False)
    current = _snapshot(101, current=True).model_copy(
        update={
            "device_good_count": 3,
            "device_power_count": 2,
            "device_position_count": 0,
        }
    )
    metrics = WardWeeklyMetrics(
        ward_id=101,
        display_name="대상",
        week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10),
        current=current,
        previous=previous,
        delta=_mock_delta(current, previous),
    )

    facts = build_fact_package(metrics)

    assert facts.summary_outline is not None
    assert facts.summary_outline.mode == "PARTIAL_DEVICE"
    assert facts.summary_outline.data_quality_code == "PARTIAL_POWER"
    assert "기기 전원 확인이 필요한 기록" in facts.summary_outline.headline
    assert "기기 전원 분리 패턴이 2회 확인" in facts.summary_outline.safety
    assert "기기 데이터 수신" in facts.allowed_topics
    assert "전원 확인이 필요해요" in facts.suggested_actions
    assert facts.summary_outline.close not in facts.suggested_actions
    assert not any("3회" in fact for fact in facts.facts)
