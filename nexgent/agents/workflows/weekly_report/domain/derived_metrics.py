"""Convert verified numbers into a small allowlisted qualitative fact package."""

from ax_contracts import WardWeeklyMetrics

from .environment_policy import EnvironmentAssessment, assess_environment
from .models import FactPackage


def build_fact_package(metrics: WardWeeklyMetrics) -> FactPackage:
    current = metrics.current
    delta = metrics.delta
    coverage = (
        "absent" if current.covered_days == 0 else "complete" if current.covered_days == 7 else "incomplete"
    )
    facts: list[str] = []
    topics: list[str] = []
    required_topics: list[str] = []
    actions: list[str] = []

    if coverage != "complete":
        facts.append("자료가 충분하지 않아 이번 주 흐름은 제한적으로 살펴봐야 합니다.")
        topics.append("자료 상태")
        actions.append("장치와 자료 수집 상태를 가볍게 확인하기")
    if current.unresolved_dispatch_count:
        facts.append("아직 마무리되지 않은 출동 요청이 있습니다.")
        topics.append("출동 요청")
        actions.append("출동 요청의 처리 상태를 확인하기")
    if current.danger_days:
        direction = _direction(delta.danger_days)
        facts.append(f"위험 감지 흐름이 지난주보다 {direction}.")
        topics.append("위험 감지")
        actions.append("최근 안부와 감지 기록을 함께 확인하기")

    environment = assess_environment(metrics)
    environment_facts, environment_actions = _environment_guidance(environment)
    if environment_facts:
        facts.extend(environment_facts)
        topics.append("실내 환경")
        required_topics.append("실내 환경")
        actions.extend(environment_actions)

    activity_direction = _direction(delta.movement_count_avg)
    if activity_direction != "비교하기 어렵습니다":
        facts.append(f"움직임 흐름이 지난주보다 {activity_direction}.")
        topics.append("활동")

    sleep_change = _direction(delta.night_awake_count_avg)
    if sleep_change not in {"비슷하게 이어졌습니다", "비교하기 어렵습니다"}:
        facts.append(f"밤중 깨어남 흐름이 지난주보다 {sleep_change}.")
        topics.append("수면")

    if not facts:
        facts.append("이번 주 생활 흐름은 지난주와 전반적으로 비슷하게 이어졌습니다.")
        topics.append("전반적인 생활 흐름")
    elif len(facts) == 1 and coverage == "complete":
        facts.append("그 밖의 생활 흐름은 전반적으로 차분하게 이어졌습니다.")
        topics.append("전반적인 생활 흐름")

    return FactPackage(
        coverage=coverage,
        facts=facts[:6],
        allowed_topics=list(dict.fromkeys(topics))[:6],
        required_topics=list(dict.fromkeys(required_topics))[:6],
        suggested_actions=list(dict.fromkeys(actions))[:3],
    )


def _direction(value: float | None) -> str:
    if value is None:
        return "비교하기 어렵습니다"
    if abs(value) < 0.000001:
        return "비슷하게 이어졌습니다"
    return "늘었습니다" if value > 0 else "줄었습니다"


def _environment_guidance(
    assessment: EnvironmentAssessment,
) -> tuple[list[str], list[str]]:
    facts: list[str] = []
    actions: list[str] = []

    if assessment.temperature_status != "unavailable":
        maximum = assessment.temperature_max
        assert maximum is not None
        if assessment.temperature_status == "good":
            facts.append("이번 주 최고 실내 온도는 해당 월 권장 범위 안이었습니다.")
        else:
            direction = "낮았습니다" if maximum < assessment.temperature_low else "높았습니다"
            degree = "크게 " if assessment.temperature_status == "risk" else ""
            facts.append(
                f"이번 주 최고 실내 온도는 해당 월 권장 범위보다 {degree}{direction}."
            )
            actions.append("실내 냉난방과 환기 상태를 가볍게 확인하기")

    if assessment.humidity_status != "unavailable":
        maximum = assessment.humidity_max
        assert maximum is not None
        if assessment.humidity_status == "good":
            facts.append("이번 주 최고 실내 습도는 적정 범위 안이었습니다.")
        else:
            direction = "낮았습니다" if maximum < assessment.humidity_low else "높았습니다"
            degree = "크게 " if assessment.humidity_status == "risk" else ""
            facts.append(f"이번 주 최고 실내 습도는 적정 범위보다 {degree}{direction}.")
            actions.append("실내 가습·제습과 환기 상태를 가볍게 확인하기")

    return facts, actions
