"""Deterministic presentation policy for weekly average risk scores."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from math import isfinite
from typing import Literal

RiskScoreStatus = Literal["unavailable", "danger", "caution", "good"]

@dataclass(frozen=True)
class RiskScoreAssessment:
    score: int | None
    status: RiskScoreStatus


def assess_risk_score(value: float | None) -> RiskScoreAssessment:
    """Round a weekly average to one point and apply approved score bands."""

    if value is None or not isfinite(value) or value < 0 or value > 100:
        return RiskScoreAssessment(score=None, status="unavailable")

    score = int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if score <= 25:
        status: RiskScoreStatus = "danger"
    elif score <= 75:
        status = "caution"
    else:
        status = "good"
    return RiskScoreAssessment(score=score, status=status)


def risk_score_description(assessment: RiskScoreAssessment) -> str:
    """Return calm guardian-facing wording for a validated score band."""

    return {
        "unavailable": "이번 주 가입자 상태 점수를 계산할 자료가 없어요.",
        "danger": "이번 주 가입자 상태 점수는 위험 범위였어요.",
        "caution": "이번 주 가입자 상태 점수는 주의 범위였어요.",
        "good": "이번 주 가입자 상태 점수는 양호 범위였어요.",
    }[assessment.status]
