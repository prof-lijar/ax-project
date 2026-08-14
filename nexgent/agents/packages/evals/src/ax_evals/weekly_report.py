"""Deterministic release-gate checks for ward-risk weekly reports."""

import re

from ax_contracts import EvaluationResult, WardWeeklyReport, WardWeeklyReportBatchResult

REQUIRED_HEADINGS = ("## 핵심 지표", "## 이번 주 요약", "## 다음 주 제안")


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
                all(heading in report.markdown for heading in REQUIRED_HEADINGS)
                and re.search(r"[가-힣]", report.markdown) is not None
                for report in result.reports
            ),
            "all reports contain the required Korean Markdown sections",
            "restore the required Korean report headings",
        ),
        _criterion(
            "personalization",
            all(
                report.markdown.startswith(
                    f"# {report.display_name} 주간 위험 리포트"
                )
                for report in result.reports
            ),
            "every report title matches its validated ward identity",
            "render each title from the report contract identity",
        ),
        _criterion(
            "numeric_grounding",
            all(_has_grounded_kpi_row(report) for report in result.reports)
            and all(not _narrative_has_digits(report) for report in result.reports),
            "danger-day rows match calculated metrics and narrative has no digits",
            "render numbers only from validated metrics and reject numeric model prose",
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
        f"| 위험 감지일 | {metrics.current.danger_days}일 | "
        f"{metrics.previous.danger_days}일 | {metrics.delta.danger_days:+d}일 |"
    )
    return expected in report.markdown


def _narrative_has_digits(report: WardWeeklyReport) -> bool:
    _, separator, narrative = report.markdown.partition("## 이번 주 요약")
    return not separator or re.search(r"\d", narrative) is not None
