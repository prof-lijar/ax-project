from datetime import date
from pathlib import Path

import pytest
from ax_contracts import (
    NarrativeGenerationMetadata,
    WardWeeklyMetrics,
    WeeklyNarrative,
    WeeklyReportRequest,
)

from workflows.weekly_report.domain.rendering import render_report
from workflows.weekly_report.domain.risk_score_policy import (
    assess_risk_score,
    risk_score_description,
)
from workflows.weekly_report.tools.source_repository import (
    MockWeeklyReportSourceRepository,
    _mock_delta,
    _snapshot,
)

_HUMAN_GOOD_SAMPLE = (
    Path(__file__).parents[2]
    / "workflows"
    / "weekly_report"
    / "examples"
    / "human-good-report.md"
)


def test_approved_sheet_example_renders_exact_markdown_template() -> None:
    current = _snapshot(101, current=True).model_copy(
        update={
            "movement_count_total": 2224.0,
            "remote_control_count_total": 0.0,
            "environment_observed_days": 7,
            "temperature_out_of_range_days": 0,
            "humidity_out_of_range_days": 0,
            "environment_out_of_range_days": 0,
            "low_temperature_days": 0,
            "high_temperature_days": 0,
            "low_humidity_days": 0,
            "high_humidity_days": 0,
            "temperature_max": 28.9,
            "temperature_min": 26.2,
            "humidity_max": 68.7,
            "humidity_min": 52.9,
            "covered_days": 7,
            "daily_summary_count": 7,
            "device_count": 1,
            "device_good_count": 7,
            "device_power_count": 0,
            "device_position_count": 0,
            "risk_detected_count": 0,
            "risk_resolved_count": 0,
            "risk_score_avg": 93.0,
        }
    )
    previous = _snapshot(101, current=False).model_copy(
        update={
            "movement_count_total": 2176.0,
            "remote_control_count_total": 0.0,
            "covered_days": 7,
            "device_count": 1,
            "risk_detected_count": 0,
            "risk_resolved_count": 0,
        }
    )
    metrics = WardWeeklyMetrics(
        ward_id=101,
        display_name="[넥스터]_김동현",
        week_start=date(2026, 8, 17),
        week_end=date(2026, 8, 24),
        current=current,
        previous=previous,
        delta=_mock_delta(current, previous),
    )
    narrative = WeeklyNarrative(
        headline=(
            "지난 한 주 [넥스터]_김동현님은 전반적으로 평소와 비슷한 "
            "생활 흐름을 이어가셨어요."
        ),
        analysis_text=(
            "생활 활동은 평소와 비슷하게 이어졌고, 생활 정보도 빠짐없이 잘 "
            "들어왔어요. 집 안 온도와 습도도 대체로 쾌적했으니 평소처럼 "
            "지켜봐 주세요."
        ),
        observations=[],
        suggestions=[],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(
            prompt_version="weekly-korean-free-summary-v28",
            validation_status="passed",
        ),
    )

    expected = _HUMAN_GOOD_SAMPLE.read_text(encoding="utf-8").rstrip("\n")
    assert report.markdown == expected
    assert report.template_data.model_dump(mode="json") == {
        "template_version": "weekly-report-v5",
        "title": "주간 생활 리포트",
        "basic_info": {
            "subscriber_name": "[넥스터]_김동현",
            "week_label": "8월 3주차",
            "period": {
                "start_date": "2026-08-17",
                "end_date": "2026-08-23",
                "display_value": "2026-08-17(월) ~ 2026-08-23(일)",
            },
            "risk_score": 93,
            "risk_score_display": "93점",
            "status": "GOOD",
            "status_description": "전반적으로 평소와 비슷한 생활 흐름을 이어가셨어요.",
        },
        "weekly_summary": (
            "지난 한 주 [넥스터]_김동현님은 전반적으로 평소와 비슷한 생활 "
            "흐름을 이어가셨어요. 생활 활동은 평소와 비슷하게 이어졌고, "
            "생활 정보도 빠짐없이 잘 들어왔어요. 집 안 온도와 습도도 대체로 "
            "쾌적했으니 평소처럼 지켜봐 주세요."
        ),
        "generation_notice": None,
        "living_activity": {
            "title": "생활 활동",
            "descriptions": [
                "활동은 비슷한 수준으로 이어졌어요.",
                "지난 주는 리모컨 이용을 살펴볼 정보가 부족했어요.",
            ],
            "tag": "비교 자료 없음",
            "activity_detection": {
                "title": "활동감지",
                "status": "GOOD",
                "metrics": {
                    "current_week": 2224.0,
                    "current_week_display": "2224회",
                    "previous_week": 2176.0,
                    "previous_week_display": "2176회",
                    "comparison_percent": pytest.approx(102.20588235294117),
                    "comparison_display": "102.2%",
                },
            },
            "remote_control_usage": {
                "title": "리모컨 이용",
                "status": "자료 없음",
                "metrics": {
                    "current_week": 0.0,
                    "current_week_display": "0회",
                    "previous_week": 0.0,
                    "previous_week_display": "0회",
                    "comparison_percent": None,
                    "comparison_display": "비교 불가",
                },
            },
        },
        "indoor_environment": {
            "title": "실내 환경",
            "status": "GOOD",
            "description": "집 안 온도와 습도가 대체로 쾌적하게 유지됐어요.",
            "tag": "쾌적",
            "metrics": {
                "observed_days": 7,
                "temperature_out_of_range_days": 0,
                "humidity_out_of_range_days": 0,
                "environment_out_of_range_days": 0,
                "temperature_max": 28.9,
                "temperature_min": 26.2,
                "humidity_max": 68.7,
                "humidity_min": 52.9,
                "observed_days_display": "7일",
                "temperature_out_of_range_days_display": "0일",
                "humidity_out_of_range_days_display": "0일",
                "environment_out_of_range_days_display": "0일",
                "temperature_max_display": "28.9℃",
                "temperature_min_display": "26.2℃",
                "humidity_max_display": "68.7%",
                "humidity_min_display": "52.9%",
            },
        },
        "device_status": {
            "title": "기기 상태",
            "status": "GOOD",
            "description": "생활 정보가 빠짐없이 잘 들어왔어요.",
            "tag": "정상",
            "metrics": {
                "normal_reception_days": 7,
                "other_count": 0,
                "power_check_days": 0,
                "position_count": 0,
                "current_covered_days": 7,
                "previous_covered_days": 7,
                "current_device_count": 1,
                "previous_device_count": 1,
                "normal_reception_days_display": "7일",
                "other_count_display": "0회",
                "power_check_days_display": "0일",
                "position_count_display": "0회",
                "current_covered_days_display": "7일",
                "previous_covered_days_display": "7일",
                "current_device_count_display": "1대",
                "previous_device_count_display": "1대",
            },
        },
        "risk_management": {
            "title": "위험 관리",
            "status": "위험 감지 없음",
            "description": "지난 한 주 위험 감지 기록은 없었어요.",
            "metrics": {
                "detected_count": 0,
                "resolved_count": 0,
                "previous_detected_count": 0,
                "previous_resolved_count": 0,
                "detected_count_display": "0회",
                "resolved_count_display": "0회",
                "previous_counts_display": "0회 / 0회",
            },
        },
        "guardian_actions": {
            "title": "보호자 행동 제안",
            "items": [
                {
                    "title": "평소와 비슷하게 지내셨어요",
                    "description": "평소와 비슷한 생활 흐름이 이어지고 있어요.",
                    "tag": "안부 전화하기",
                    "template_id": "GUI_GOOD_01",
                }
            ],
            "empty_message": None,
            "template_id": None,
        },
    }


def test_activity_signals_render_inside_one_living_activity_section() -> None:
    current = _snapshot(101, current=True).model_copy(
        update={
            "movement_count_total": 3607.0,
            "remote_control_count_total": 5075.0,
        }
    )
    previous = _snapshot(101, current=False).model_copy(
        update={
            "movement_count_total": 3240.0,
            "remote_control_count_total": 1355.0,
        }
    )
    metrics = WardWeeklyMetrics(
        ward_id=101,
        display_name="테스트 가입자",
        week_start=date(2026, 8, 17),
        week_end=date(2026, 8, 24),
        current=current,
        previous=previous,
        delta=_mock_delta(current, previous),
    )

    report = render_report(
        metrics,
        WeeklyNarrative(
            headline="지난 한 주 테스트 가입자님은 생활 흐름을 이어가셨습니다.",
            analysis_text="구체적으로 확인된 생활 흐름을 살펴봤습니다.",
        ),
        "llm",
        NarrativeGenerationMetadata(
            prompt_version="weekly-korean-sheet-template-v16",
            validation_status="passed",
        ),
    )

    expected = """## 생활 활동

설명:
- 활동은 비슷한 수준으로 이어졌어요.
- TV 이용 등 일상적인 생활 패턴이 많이 늘었어요. 최근 생활에 달라진 점이 있는지 살펴봐 주세요.
- 태그: 많이 증가

### 활동감지

- 상태: GOOD
- 지난 한 주: 3607회
- 2주 전: 3240회
- 2주 전과 비교: 111.3%

---

### 리모컨 이용

- 상태: RISK
- 지난 한 주: 5075회
- 2주 전: 1355회
- 2주 전과 비교: 374.5%"""
    assert expected in report.markdown
    assert "## 1. 활동량" not in report.markdown


@pytest.mark.parametrize(
    (
        "movement_current",
        "movement_previous",
        "remote_current",
        "remote_previous",
        "descriptions",
        "expected_tag",
    ),
    [
        (
            100.0,
            0.0,
            100.0,
            100.0,
            [
                "지난 주는 활동 감지를 살펴볼 정보가 부족했어요.",
                "TV 이용 등 일상적인 생활 패턴도 비슷하게 이어졌어요.",
            ],
            "비교 자료 없음",
        ),
        (
            100.0,
            100.0,
            100.0,
            0.0,
            [
                "활동은 비슷한 수준으로 이어졌어요.",
                "지난 주는 리모컨 이용을 살펴볼 정보가 부족했어요.",
            ],
            "비교 자료 없음",
        ),
        (
            100.0,
            0.0,
            100.0,
            0.0,
            ["지난 주는 생활 활동을 살펴볼 정보가 부족했어요."],
            "비교 자료 없음",
        ),
        (
            30.0,
            100.0,
            100.0,
            0.0,
            [
                "활동이 많이 줄었어요. 안부를 한 번 확인해 주세요.",
                "지난 주는 리모컨 이용을 살펴볼 정보가 부족했어요.",
            ],
            "많이 감소",
        ),
        (
            50.0,
            100.0,
            200.0,
            100.0,
            [
                "활동이 조금 줄어든 모습이에요.",
                "TV 이용 등 일상적인 생활 패턴이 조금 늘었어요.",
            ],
            "조금 감소",
        ),
        (
            30.0, 100.0, 30.0, 100.0,
            [
                "활동이 많이 줄었어요.",
                "TV 이용 등 일상적인 생활 패턴이 많이 줄었어요. 안부를 한 번 확인해 주세요.",
            ],
            "많이 감소",
        ),
        (
            300.0, 100.0, 300.0, 100.0,
            [
                "활동이 많이 늘었어요.",
                "TV 이용 등 일상적인 생활 패턴이 많이 늘었어요. 최근 생활에 달라진 점이 있는지 살펴봐 주세요.",
            ],
            "많이 증가",
        ),
        (
            30.0, 100.0, 300.0, 100.0,
            [
                "활동이 많이 줄었어요. 안부를 한 번 확인해 주세요.",
                "TV 이용 등 일상적인 생활 패턴이 많이 늘었어요. 최근 생활에 달라진 점이 있는지 살펴봐 주세요.",
            ],
            "많이 감소",
        ),
        (
            100.0, 100.0, 30.0, 100.0,
            [
                "활동은 비슷한 수준으로 이어졌어요.",
                "TV 이용 등 일상적인 생활 패턴이 많이 줄었어요. 안부를 한 번 확인해 주세요.",
            ],
            "많이 감소",
        ),
        (
            100.0, 100.0, 200.0, 100.0,
            [
                "활동은 비슷한 수준으로 이어졌어요.",
                "TV 이용 등 일상적인 생활 패턴이 조금 늘었어요.",
            ],
            "조금 증가",
        ),
    ],
)
def test_activity_section_combines_descriptions(
    movement_current: float,
    movement_previous: float,
    remote_current: float,
    remote_previous: float,
    descriptions: list[str],
    expected_tag: str,
) -> None:
    current = _snapshot(101, current=True).model_copy(
        update={
            "movement_count_total": movement_current,
            "remote_control_count_total": remote_current,
        }
    )
    previous = _snapshot(101, current=False).model_copy(
        update={
            "movement_count_total": movement_previous,
            "remote_control_count_total": remote_previous,
        }
    )
    metrics = WardWeeklyMetrics(
        ward_id=101,
        display_name="테스트 가입자",
        week_start=date(2026, 8, 17),
        week_end=date(2026, 8, 24),
        current=current,
        previous=previous,
        delta=_mock_delta(current, previous),
    )

    report = render_report(
        metrics,
        WeeklyNarrative(headline="지난 한 주를 살펴봤어요."),
        "llm",
        NarrativeGenerationMetadata(
            prompt_version="test",
            validation_status="passed",
        ),
    )

    assert report.template_data.living_activity.descriptions == descriptions
    assert report.template_data.living_activity.tag == expected_tag
    assert f"- 태그: {expected_tag}" in report.markdown
    for description in descriptions:
        assert f"- {description}" in report.markdown
    activity_markdown = report.markdown.split("## 생활 활동\n", 1)[1].split(
        "### 활동감지", 1
    )[0]
    for action in (
        "안부를 한 번 확인해 주세요.",
        "생활에 달라진 점이 있는지 살펴봐 주세요.",
    ):
        assert " ".join(descriptions).count(action) <= 1
        assert activity_markdown.count(action) <= 1


@pytest.mark.parametrize(
    ("missing_temperature", "missing_humidity", "expected_description"),
    [
        (True, False, "지난 주는 온도를 살펴볼 정보가 부족했어요."),
        (False, True, "지난 주는 습도를 살펴볼 정보가 부족했어요."),
        (True, True, "지난 주는 실내 환경을 살펴볼 정보가 부족했어요."),
    ],
)
def test_environment_section_uses_specific_missing_data_copy_and_dash_values(
    missing_temperature: bool,
    missing_humidity: bool,
    expected_description: str,
) -> None:
    current = _snapshot(101, current=True).model_copy(
        update={
            "temperature_avg": None if missing_temperature else 23.5,
            "temperature_min": None if missing_temperature else 26.0,
            "temperature_max": None if missing_temperature else 28.0,
            "temperature_count": 0 if missing_temperature else 84,
            "humidity_avg": None if missing_humidity else 50.0,
            "humidity_min": None if missing_humidity else 40.0,
            "humidity_max": None if missing_humidity else 58.0,
            "humidity_count": 0 if missing_humidity else 84,
            "environment_observed_days": None,
            "temperature_out_of_range_days": None,
            "humidity_out_of_range_days": None,
            "environment_out_of_range_days": None,
            "low_temperature_days": None,
            "cool_temperature_days": None,
            "high_temperature_days": None,
            "low_humidity_days": None,
            "high_humidity_days": None,
            "humidity_at_or_above_70_days": None,
        }
    )
    previous = _snapshot(101, current=False)
    metrics = WardWeeklyMetrics(
        ward_id=101,
        display_name="테스트 가입자",
        week_start=date(2026, 8, 17),
        week_end=date(2026, 8, 24),
        current=current,
        previous=previous,
        delta=_mock_delta(current, previous),
    )

    report = render_report(
        metrics,
        WeeklyNarrative(headline="지난 한 주를 살펴봤어요."),
        "llm",
        NarrativeGenerationMetadata(
            prompt_version="test",
            validation_status="passed",
        ),
    )
    rendered = report.template_data.indoor_environment

    assert rendered.description == expected_description
    assert f"- 설명: {expected_description}" in report.markdown
    assert rendered.metrics.observed_days is None
    assert rendered.metrics.observed_days_display == "-"
    assert "- 온습도 관측일: -" in report.markdown
    assert rendered.metrics.temperature_max_display == (
        "-" if missing_temperature else "28℃"
    )
    assert rendered.metrics.humidity_max_display == (
        "-" if missing_humidity else "58%"
    )


def test_risk_score_description_uses_approved_good_copy() -> None:
    description = risk_score_description(assess_risk_score(86))

    assert description == "전반적으로 평소와 비슷한 생활 흐름을 이어가셨어요."


@pytest.mark.asyncio
async def test_report_uses_guardian_facing_section_template() -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0].model_copy(update={"display_name": "주필기"})
    narrative = WeeklyNarrative(
        headline=(
            "지난 한 주 주필기님은 전반적으로 평소와 비슷한 생활 흐름을 "
            "이어가셨어요."
        ),
        analysis_text=(
            "생활 활동과 TV 이용 등 일상적인 패턴도 비슷하게 이어졌고, 집 안 "
            "환경과 생활 정보 수신 상태도 함께 확인했어요."
        ),
        observations=["생활 흐름에 일부 변화가 보였어요."],
        suggestions=["최근 안부를 편안하게 확인해 보셔도 좋아요."],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(
            prompt_version="test",
            validation_status="passed",
        ),
    )

    assert report.markdown.startswith("# 주간 생활 리포트")
    assert "- 가입자: 주필기" in report.markdown
    assert "- 주차: 8월 1주차" in report.markdown
    assert "- 기간: 2026-08-03(월) ~ 2026-08-09(일)" in report.markdown
    assert "- 가입자 상태 점수: 86점" in report.markdown
    assert "- 상태: GOOD" in report.markdown
    assert (
        "- 상태 안내: 전반적으로 평소와 비슷한 생활 흐름을 이어가셨어요."
        in report.markdown
    )
    assert (
        "지난 한 주 주필기님은 전반적으로 평소와 비슷한 생활 흐름을 이어가셨어요."
        in report.markdown
    )
    assert "점수 범위:" not in report.markdown
    assert "## 한주 총평" in report.markdown
    assert "이번 주에는" not in report.markdown
    assert "수면" not in report.markdown
    assert "출동" not in report.markdown
    assert "## 생활 활동\n\n설명:" in report.markdown
    assert "- 활동은 비슷한 수준으로 이어졌어요." in report.markdown
    assert "- 태그: 평소 수준" in report.markdown
    assert "### 활동감지\n\n- 상태: GOOD" in report.markdown
    assert "### 리모컨 이용\n\n- 상태: GOOD" in report.markdown
    assert "## 생활 패턴" not in report.markdown
    assert "## 1. 활동량" not in report.markdown
    assert "### 움직임" not in report.markdown
    assert "### 리모컨 사용" not in report.markdown
    assert "### 지표" not in report.markdown.split("## 실내 환경", 1)[0]
    assert "- 움직임 합계" not in report.markdown
    assert "- 리모컨 사용 합계" not in report.markdown
    assert "- 2주 전과 비교: 112.5%" in report.markdown
    assert "## 기기 상태" in report.markdown
    assert "## 기기 상태\n\n- 상태: GOOD" in report.markdown
    assert "- 설명: 생활 정보가 빠짐없이 잘 들어왔어요." in report.markdown
    assert "- 태그: 정상" in report.markdown
    assert "- 정보 수신: 7일" in report.markdown
    assert "- 기타 수신 패턴: 0회" in report.markdown
    assert "- 전원 확인: 0일" in report.markdown
    assert "- 기기 위치 확인 패턴: 0회" in report.markdown
    assert "### 위험 관리 기록" not in report.markdown
    assert (
        "상세 기록은 현재 주간 리포트 데이터에 포함되지 않아요." not in report.markdown
    )
    assert "# 보호자 행동 제안" in report.markdown
    assert "- 확인된 자료를 바탕으로 한 별도 행동 제안은 없어요." in (report.markdown)
    assert "- template_id: GUI_GOOD_01" in report.markdown
    assert report.template_data.guardian_actions.template_id == "GUI_GOOD_01"
    assert "생활 흐름에 일부 변화가 보였어요." not in report.markdown
    assert "- 권장 행동:" not in report.markdown


@pytest.mark.asyncio
async def test_report_requests_power_check_when_device_rows_are_missing() -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    metrics = metrics.model_copy(
        update={
            "current": metrics.current.model_copy(
                update={
                    "covered_days": 0,
                    "daily_summary_count": 0,
                    "device_count": 0,
                    "device_good_count": None,
                    "device_power_count": None,
                    "device_position_count": None,
                }
            ),
            "delta": metrics.delta.model_copy(update={"covered_days": -7}),
        }
    )
    narrative = WeeklyNarrative(
        headline="지난 한 주 생활 흐름을 살펴봤어요.",
        analysis_text="확인된 생활 흐름을 정리했습니다.",
    )

    report = render_report(
        metrics,
        narrative,
        "template_fallback",
        NarrativeGenerationMetadata(
            prompt_version="test",
            validation_status="fallback",
        ),
    )

    assert "## 기기 상태\n\n- 상태: 자료 없음" in report.markdown
    assert "- 설명: 기기 전원이 연결되어 있는지 확인해 주세요." in report.markdown
    assert "- 정보 수신: 0일" in report.markdown
    assert "- 기타 수신 패턴: 0" in report.markdown
    assert "- 전원 확인: 7일" in report.markdown
    assert "- 기기 위치 확인 패턴: 0" in report.markdown
    assert report.template_data.device_status.metrics.normal_reception_days == 0
    assert report.template_data.device_status.metrics.power_check_days == 7


@pytest.mark.asyncio
async def test_device_day_metrics_use_covered_days_and_period_remainder() -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    metrics = metrics.model_copy(
        update={
            "current": metrics.current.model_copy(
                update={
                    "covered_days": 3,
                    "daily_summary_count": 3,
                    "device_good_count": 3,
                    "device_power_count": 0,
                    "device_position_count": 0,
                }
            ),
            "delta": metrics.delta.model_copy(
                update={"covered_days": 3 - metrics.previous.covered_days}
            ),
        }
    )

    report = render_report(
        metrics,
        WeeklyNarrative(headline="지난 한 주를 살펴봤어요."),
        "llm",
        NarrativeGenerationMetadata(
            prompt_version="test",
            validation_status="passed",
        ),
    )

    device_metrics = report.template_data.device_status.metrics
    assert device_metrics.normal_reception_days == 3
    assert device_metrics.normal_reception_days_display == "3일"
    assert device_metrics.power_check_days == 4
    assert device_metrics.power_check_days_display == "4일"
    assert "- 정보 수신: 3일" in report.markdown
    assert "- 전원 확인: 4일" in report.markdown
    assert "전원 확인 패턴" not in report.markdown


@pytest.mark.asyncio
async def test_report_labels_available_device_rows_without_claiming_no_data() -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    metrics = metrics.model_copy(
        update={
            "current": metrics.current.model_copy(
                update={
                    "device_good_count": 6,
                    "device_power_count": 0,
                    "device_position_count": 0,
                }
            )
        }
    )
    narrative = WeeklyNarrative(
        headline="지난 한 주 기기 수신 상태는 안정적으로 유지되었습니다.",
        analysis_text=("구체적으로 확인된 기기 데이터는 정상적으로 수집되었습니다."),
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert "## 기기 상태\n\n- 상태: GOOD" in report.markdown
    assert "- 설명: 생활 정보가 빠짐없이 잘 들어왔어요." in report.markdown
    assert "- 태그: 정상" in report.markdown
    assert "- 정보 수신: 7일" in report.markdown
    assert "- 기타 수신 패턴: 1회" in report.markdown
    assert "지난 한 주 기기 데이터 수신이 확인되지 않았어요." not in report.markdown
    assert "기기 전원이 연결되어 있는지 확인해 주세요" not in report.markdown


@pytest.mark.parametrize("night_awake_count", [None, 0.0])
@pytest.mark.asyncio
async def test_report_omits_sleep_section_regardless_of_source_metrics(
    night_awake_count: float | None,
) -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    metrics = metrics.model_copy(
        update={
            "current": metrics.current.model_copy(
                update={
                    "sleep_time_avg": None,
                    "wake_up_time_avg": None,
                    "night_awake_count_avg": night_awake_count,
                }
            ),
            "previous": metrics.previous.model_copy(
                update={
                    "sleep_time_avg": None,
                    "wake_up_time_avg": None,
                    "night_awake_count_avg": night_awake_count,
                }
            ),
            "delta": metrics.delta.model_copy(
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
    narrative = WeeklyNarrative(
        headline="지난 한 주 생활 흐름을 살펴봤어요.",
        analysis_text=(
            "지난 한 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료를 2주 전과 함께 살펴봤어요. "
            "측정된 변화만으로 이유를 단정하지 않았어요. "
            "평소 모습과 함께 편안하게 살펴보셔도 좋아요."
        ),
        observations=["생활 흐름을 확인했어요."],
        suggestions=["최근 안부를 편안하게 확인해 보셔도 좋아요."],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert "수면 패턴" not in report.markdown
    assert "평균 취침 시간" not in report.markdown
    assert "출동" not in report.markdown
    assert "## 생활 활동" in report.markdown
    assert "### 활동감지" in report.markdown
    assert "### 리모컨 이용" in report.markdown
    assert "## 생활 패턴" not in report.markdown
    assert "## 실내 환경" in report.markdown
    assert "## 기기 상태" in report.markdown
    assert "## 위험 관리" in report.markdown
    assert "## 2. 실내 환경" not in report.markdown
    assert "## 3. 기기 상태" not in report.markdown
    assert "## 4. 위험 관리" not in report.markdown


@pytest.mark.asyncio
async def test_report_renders_approved_monthly_environment_ranges() -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    narrative = WeeklyNarrative(
        headline="지난 한 주 생활 흐름을 살펴봤어요.",
        analysis_text=(
            "지난 한 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료를 2주 전과 함께 살펴봤어요. "
            "측정된 변화만으로 이유를 단정하지 않았어요. "
            "평소 모습과 함께 편안하게 살펴보셔도 좋아요."
        ),
        observations=["생활 흐름을 확인했어요."],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(
            prompt_version="test",
            validation_status="passed",
        ),
    )

    assert "## 실내 환경\n\n- 상태: GOOD" in report.markdown
    assert "- 설명: 집 안 온도와 습도가 대체로 쾌적하게 유지됐어요." in report.markdown
    assert "- 태그: 쾌적" in report.markdown
    assert "- 온습도 관측일: 7일" in report.markdown
    assert "- 온도 권장범위 이탈: 0일" in report.markdown
    assert "- 습도 권장범위 이탈: 0일" in report.markdown
    assert "15℃ 초과 ~ 31℃ 미만" not in report.markdown
    assert "30% 초과 ~ 70% 미만" not in report.markdown


@pytest.mark.parametrize(
    ("counts", "status", "feedback", "summary"),
    [
        (
            {
                "temperature_out_of_range_days": 1,
                "environment_out_of_range_days": 1,
                "high_temperature_days": 1,
            },
            "GOOD",
            "집 안 온도와 습도가 대체로 쾌적하게 유지됐어요.",
            "쾌적",
        ),
        (
            {
                "temperature_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "high_temperature_days": 2,
            },
            "CAUTION",
            "집 안이 조금 더운 날이 있었어요. 냉방이나 환기 상태를 한 번 살펴봐 주세요.",
            "조금 더움",
        ),
        (
            {
                "humidity_out_of_range_days": 2,
                "environment_out_of_range_days": 2,
                "high_humidity_days": 2,
            },
            "CAUTION",
            "집 안이 습한 날이 있었어요. 제습이나 환기가 필요한지 살펴봐 주세요.",
            "습함",
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_temperature_days": 4,
            },
            "RISK",
            "집 안이 많이 더운 날이 여러 번 이어졌어요. 냉방이 잘 되고 있는지 조금 더 세심하게 살펴봐 주세요.",
            "더운 날 이어짐",
        ),
        (
            {
                "temperature_out_of_range_days": 4,
                "humidity_out_of_range_days": 4,
                "environment_out_of_range_days": 4,
                "high_temperature_days": 4,
                "high_humidity_days": 4,
            },
            "RISK",
            "덥고 습한 날이 여러 번 이어졌어요. 냉방과 환기가 잘 되고 있는지 조금 더 세심하게 살펴봐 주세요.",
            "덥고 습한 날 이어짐",
        ),
    ],
)
@pytest.mark.asyncio
async def test_report_gives_approved_feedback_from_environment_day_counts(
    counts: dict[str, int],
    status: str,
    feedback: str,
    summary: str,
) -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0].model_copy(
        update={"current": source.items[0].current.model_copy(update=counts)}
    )
    narrative = WeeklyNarrative(
        headline="지난 한 주 생활 흐름을 살펴봤어요.",
        analysis_text=(
            "지난 한 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료를 2주 전과 함께 살펴봤어요. "
            "측정된 변화만으로 이유를 단정하지 않았어요. "
            "평소 모습과 함께 편안하게 살펴보셔도 좋아요."
        ),
        observations=["생활 흐름을 확인했어요."],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert f"- 상태: {status}" in report.markdown
    assert f"- 설명: {feedback}" in report.markdown
    assert f"- 태그: {summary}" in report.markdown


@pytest.mark.parametrize(
    ("average", "score", "status", "description"),
    [
        (
            0.0,
            "0점",
            "RISK",
            "평소와 다른 생활 모습이 크게 보여요. 안부를 조금 더 세심하게 확인해 주세요.",
        ),
        (
            25.49,
            "25점",
            "RISK",
            "평소와 다른 생활 모습이 크게 보여요. 안부를 조금 더 세심하게 확인해 주세요.",
        ),
        (
            25.5,
            "26점",
            "CAUTION",
            "평소와 조금 다른 생활 모습이 보여요. 한 번 더 살펴봐 주세요.",
        ),
        (
            75.49,
            "75점",
            "CAUTION",
            "평소와 조금 다른 생활 모습이 보여요. 한 번 더 살펴봐 주세요.",
        ),
        (
            75.5,
            "76점",
            "GOOD",
            "전반적으로 평소와 비슷한 생활 흐름을 이어가셨어요.",
        ),
        (
            100.0,
            "100점",
            "GOOD",
            "전반적으로 평소와 비슷한 생활 흐름을 이어가셨어요.",
        ),
    ],
)
@pytest.mark.asyncio
async def test_report_classifies_rounded_weekly_average_risk_score(
    average: float,
    score: str,
    status: str,
    description: str,
) -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    current = metrics.current.model_copy(update={"risk_score_avg": average})
    previous = metrics.previous
    metrics = metrics.model_copy(
        update={
            "current": current,
            "delta": metrics.delta.model_copy(
                update={"risk_score_avg": average - previous.risk_score_avg}
            ),
        }
    )
    narrative = WeeklyNarrative(
        headline="지난 한 주 생활 흐름을 살펴봤어요.",
        analysis_text=(
            "지난 한 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료를 2주 전과 함께 살펴봤어요. "
            "측정된 변화만으로 이유를 단정하지 않았어요. "
            "평소 모습과 함께 편안하게 살펴보셔도 좋아요."
        ),
        observations=["생활 흐름을 확인했어요."],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert f"- 가입자 상태 점수: {score}" in report.markdown
    assert f"- 상태: {status}" in report.markdown
    assert f"- 상태 안내: {description}" in report.markdown


@pytest.mark.asyncio
async def test_report_discloses_missing_weekly_average_risk_score() -> None:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    metrics = metrics.model_copy(
        update={
            "current": metrics.current.model_copy(update={"risk_score_avg": None}),
            "delta": metrics.delta.model_copy(update={"risk_score_avg": None}),
        }
    )
    narrative = WeeklyNarrative(
        headline="지난 한 주 생활 흐름을 살펴봤어요.",
        analysis_text=(
            "지난 한 주 생활 흐름은 전반적으로 차분하게 이어졌어요. "
            "확인된 자료를 2주 전과 함께 살펴봤어요. "
            "측정된 변화만으로 이유를 단정하지 않았어요. "
            "평소 모습과 함께 편안하게 살펴보셔도 좋아요."
        ),
        observations=["생활 흐름을 확인했어요."],
    )

    report = render_report(
        metrics,
        narrative,
        "llm",
        NarrativeGenerationMetadata(prompt_version="test", validation_status="passed"),
    )

    assert "- 가입자 상태 점수: 자료 없음" in report.markdown
    assert "- 상태: 자료 없음" in report.markdown
    assert "지난 한 주 상태 점수를 계산할 자료가 없어요." in report.markdown
