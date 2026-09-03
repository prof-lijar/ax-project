"""Deterministic release gates for grounded, warm weekly reports."""

import re

from ax_contracts import EvaluationResult, WardWeeklyReport, WardWeeklyReportBatchResult

REQUIRED_HEADINGS = (
    "## 기본 정보",
    "## 한주 총평",
    "# 주요 내용",
    "# 보호자 행동 제안",
)
FORBIDDEN_PHRASES = (
    "위험합니다",
    "응급",
    "진단",
    "반드시",
    "확실히",
    "하세요",
    "하십시오",
)

BULK_TARGET_REPORTS = 10_000
BULK_SLA_SECONDS = 2 * 60 * 60
BULK_HEALTHY_SECONDS = 90 * 60


def evaluate_weekly_report_bulk_capacity(
    observed_reports_per_second: float,
) -> list[EvaluationResult]:
    """Turn a representative end-to-end benchmark into explicit SLA gates."""

    if observed_reports_per_second <= 0:
        raise ValueError("observed_reports_per_second must be positive")
    projected_seconds = BULK_TARGET_REPORTS / observed_reports_per_second
    return [
        _criterion(
            "bulk_two_hour_sla",
            projected_seconds <= BULK_SLA_SECONDS,
            f"projected {projected_seconds:.1f}s for {BULK_TARGET_REPORTS} reports",
            "add inference capacity or reduce per-report latency before release",
        ),
        _criterion(
            "bulk_ninety_minute_headroom",
            projected_seconds <= BULK_HEALTHY_SECONDS,
            f"projected {projected_seconds:.1f}s for {BULK_TARGET_REPORTS} reports",
            "scale workers/model replicas until the ninety-minute healthy target passes",
        ),
    ]


def evaluate_weekly_report_batch(
    result: WardWeeklyReportBatchResult,
) -> list[EvaluationResult]:
    """Evaluate observable batch, format, identity, and grounding behavior."""

    return [
        _criterion(
            "batch_completeness",
            bool(result.reports)
            and [report.ward_id for report in result.reports]
            == sorted(report.ward_id for report in result.reports),
            f"validated {len(result.reports)} sorted unique ward reports",
            "return at least one report and sort reports by ward_id",
        ),
        _criterion(
            "korean_markdown_structure",
            all(
                _has_required_headings(report)
                and re.search(r"[가-힣]", report.markdown) is not None
                for report in result.reports
            ),
            "all reports contain the required Korean Markdown sections",
            "restore the required Korean report headings",
        ),
        _criterion(
            "personalization",
            all(
                report.markdown.startswith("# 주간 생활 리포트")
                and f"- 가입자: {report.display_name}" in report.markdown
                for report in result.reports
            ),
            "every report identifies its validated ward in the basic information",
            "render each ward identity in the basic information section",
        ),
        _criterion(
            "numeric_grounding",
            all(_has_grounded_kpi_row(report) for report in result.reports)
            and all(
                _narrative_numbers_are_grounded(report) for report in result.reports
            ),
            "risk-event rows and significant narrative counts match calculated metrics",
            "render only allowlisted significant values from validated metrics",
        ),
        _criterion(
            "device_reception_consistency",
            all(_has_consistent_device_reception(report) for report in result.reports),
            "device status, unmatched-row count, and guardian copy match source-row evidence",
            "apply power/position precedence, then GOOD for any good occurrence, and reserve missing-data power guidance for zero source rows",
        ),
        _criterion(
            "narrative_safety",
            all(
                _narrative_numbers_are_grounded(report)
                and not any(
                    phrase in _narrative_text(report) for phrase in FORBIDDEN_PHRASES
                )
                for report in result.reports
            ),
            "narrative uses only grounded significant counts and avoids categorical language",
            "regenerate unsafe narrative or use the deterministic fallback",
        ),
        _criterion(
            "fallback_disclosure",
            all(
                report.generation_mode != "template_fallback"
                or "자동 대체됨" in report.markdown
                for report in result.reports
            ),
            "every template fallback is disclosed in its report",
            "label reports that use deterministic fallback prose",
        ),
    ]


def weekly_report_release_ready(results: list[EvaluationResult]) -> bool:
    return bool(results) and all(result.status == "passed" for result in results)


def _criterion(
    name: str,
    passed: bool,
    evidence: str,
    recommendation: str,
) -> EvaluationResult:
    return EvaluationResult(
        criterion=name,
        status="passed" if passed else "failed",
        severity="info" if passed else "error",
        score=1.0 if passed else 0.0,
        evidence=[evidence],
        recommendation=None if passed else recommendation,
    )


def _has_grounded_kpi_row(report: WardWeeklyReport) -> bool:
    metrics = report.metrics
    expected = (
        f"  - 위험 감지: {metrics.current.risk_detected_count}회\n"
        f"  - 정상 해제: {metrics.current.risk_resolved_count}회\n"
        f"  - 2주 전: {metrics.previous.risk_detected_count}회 / "
        f"{metrics.previous.risk_resolved_count}회"
    )
    return expected in report.markdown


def _has_required_headings(report: WardWeeklyReport) -> bool:
    if not all(heading in report.markdown for heading in REQUIRED_HEADINGS):
        return False
    detail_headings = (
        "## 생활 활동",
        "### 활동감지",
        "### 리모컨 이용",
        "## 실내 환경",
        "## 기기 상태",
        "## 위험 관리",
    )
    return all(heading in report.markdown for heading in detail_headings)


def _has_consistent_device_reception(report: WardWeeklyReport) -> bool:
    current = report.metrics.current
    counts = (
        current.device_good_count,
        current.device_power_count,
        current.device_position_count,
    )
    if current.daily_summary_count == 0:
        return "## 기기 상태\n\n- 상태: 자료 없음" in report.markdown
    if any(value is None for value in counts):
        return False

    other_count = current.daily_summary_count - sum(value or 0 for value in counts)
    if f"- 기타 수신 패턴: {other_count}회" not in report.markdown:
        return False
    if "지난 한 주 기기 데이터 수신이 확인되지 않았어요." in report.markdown:
        return False

    if (current.device_power_count or 0) >= 2 or (
        current.device_position_count or 0
    ) >= 2:
        expected_status = "CAUTION"
    elif (current.device_good_count or 0) >= 1:
        expected_status = "GOOD"
        if "기기 전원이 연결되어 있는지 확인해 주세요" in report.markdown:
            return False
    else:
        expected_status = "판정 불가"
    return f"## 기기 상태\n\n- 상태: {expected_status}" in report.markdown


def _narrative_numbers_are_grounded(report: WardWeeklyReport) -> bool:
    narrative = _narrative_text(report).replace("2주 전", "")
    numbers = re.findall(r"\d+(?:\.\d+)?", narrative)
    if not numbers:
        return True

    current = report.metrics.current
    allowed = set(re.findall(r"\d+(?:\.\d+)?", report.display_name))
    if current.covered_days < 4:
        allowed.add(str(current.covered_days))
    if (current.device_power_count or 0) >= 2:
        allowed.add(str(current.device_power_count))
    if (current.device_position_count or 0) >= 2:
        allowed.add(str(current.device_position_count))
    return all(number in allowed for number in numbers)


def _narrative_text(report: WardWeeklyReport) -> str:
    narrative = report.narrative
    return " ".join(
        [
            narrative.headline,
            narrative.analysis_text,
            *narrative.observations,
            *narrative.suggestions,
        ]
    )
