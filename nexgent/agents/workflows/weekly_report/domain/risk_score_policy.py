"""Deterministic presentation policy for weekly average risk scores."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from math import isfinite
from typing import Literal

RiskScoreStatus = Literal["UNAVAILABLE", "RISK", "CAUTION", "GOOD"]


@dataclass(frozen=True)
class RiskScoreAssessment:
    score: int | None
    status: RiskScoreStatus


def assess_risk_score(value: float | None) -> RiskScoreAssessment:
    """Round a weekly average to one point and apply approved score bands."""

    if value is None or not isfinite(value) or value < 0 or value > 100:
        return RiskScoreAssessment(score=None, status="UNAVAILABLE")

    score = int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if score <= 25:
        status: RiskScoreStatus = "RISK"
    elif score <= 75:
        status = "CAUTION"
    else:
        status = "GOOD"
    return RiskScoreAssessment(score=score, status=status)


def risk_score_status_label(assessment: RiskScoreAssessment) -> str:
    """Return the report-facing status code or the unavailable disclosure."""

    if assessment.status == "UNAVAILABLE":
        return "자료 없음"
    return assessment.status


def risk_score_description(
    assessment: RiskScoreAssessment,
) -> str:
    """Return approved guardian-facing wording for a validated score band."""

    return {
        "UNAVAILABLE": "지난 한 주 상태 점수를 계산할 자료가 없어요.",
        "RISK": "지난 한 주는 즉시 확인이 필요한 위험 신호가 확인됐어요.",
        "CAUTION": "지난 한 주는 평소와 다른 흐름이 일부 확인됐어요.",
        "GOOD": "지난 한 주는 대체로 안정적인 상태가 유지됐어요.",
    }[assessment.status]
