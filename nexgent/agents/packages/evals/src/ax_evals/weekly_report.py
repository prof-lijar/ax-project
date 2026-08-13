"""Deterministic release-gate checks for personal weekly reports."""

import re

from ax_contracts import EvaluationResult, UserWeeklyReport, WeeklyReportBatchResult

REQUIRED_HEADINGS = ("## 핵심 지표", "## 이번 주 요약", "## 다음 주 제안")


def evaluate_weekly_report_batch(
    result: WeeklyReportBatchResult,
) -> list[EvaluationResult]:
    """Evaluate observable batch, format, identity, and grounding behavior."""

    checks = [
        _criterion(
            "batch_completeness",
            bool(result.reports)
            and [report.user_id for report in result.reports]
            == sorted(report.user_id for report in result.reports),
            f"validated {len(result.reports)} sorted unique reports",
            "return at least one report and sort reports by user_id",
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
                    f"# {report.display_name}님의 주간 업무 리포트"
                )
                for report in result.reports
            ),
            "every report title matches its validated user identity",
            "render each title from the report contract identity",
        ),
        _criterion(
            "numeric_grounding",
            all(_has_grounded_kpi_rows(report) for report in result.reports)
            and all(not _narrative_has_digits(report) for report in result.reports),
            "KPI rows match calculated metrics and narrative sections contain no digits",
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
    return checks


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


def _has_grounded_kpi_rows(report: UserWeeklyReport) -> bool:
    current = report.metrics.current
    previous = report.metrics.previous
    delta = report.metrics.delta
    rows = (
        f"| 배정 업무 | {current.assigned_tasks}건 | {previous.assigned_tasks}건 | {_signed(delta.assigned_tasks, '건')} |",
        f"| 완료 업무 | {current.completed_tasks}건 | {previous.completed_tasks}건 | {_signed(delta.completed_tasks, '건')} |",
        f"| 완료율 | {current.completion_rate_percent:.1f}% | {previous.completion_rate_percent:.1f}% | {_signed(delta.completion_rate_percentage_points, '%p', one_decimal=True)} |",
        f"| 집중 시간 | {_duration(current.focus_minutes)} | {_duration(previous.focus_minutes)} | {_signed(delta.focus_minutes, '분')} |",
        f"| 활동일 | {current.active_days}일 | {previous.active_days}일 | {_signed(delta.active_days, '일')} |",
        f"| 새 블로커 | {current.blockers_opened}건 | {previous.blockers_opened}건 | {_signed(delta.blockers_opened, '건')} |",
        f"| 해결 블로커 | {current.blockers_resolved}건 | {previous.blockers_resolved}건 | {_signed(delta.blockers_resolved, '건')} |",
    )
    return all(row in report.markdown for row in rows)


def _narrative_has_digits(report: UserWeeklyReport) -> bool:
    _, separator, narrative = report.markdown.partition("## 이번 주 요약")
    return not separator or re.search(r"\d", narrative) is not None


def _duration(minutes: int) -> str:
    hours, remainder = divmod(minutes, 60)
    return f"{hours}시간 {remainder}분"


def _signed(value: float, unit: str, *, one_decimal: bool = False) -> str:
    rendered = f"{value:+.1f}" if one_decimal else f"{int(value):+d}"
    return f"{rendered}{unit}"
