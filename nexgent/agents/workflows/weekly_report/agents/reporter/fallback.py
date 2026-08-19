"""Warm deterministic narrative used when model output cannot be trusted."""

from ax_contracts import WeeklyNarrative

from workflows.weekly_report.domain.models import FactPackage

from .policy import validate_narrative


def build_fallback(facts: FactPackage) -> WeeklyNarrative:
    first_fact = facts.facts[0]
    second_fact = facts.facts[1] if len(facts.facts) > 1 else "그 밖의 생활 흐름은 차분하게 이어졌습니다."
    analysis = (
        f"이번 주 생활 흐름을 살펴보니 {first_fact} "
        f"함께 확인한 내용에서는 {second_fact} "
        "측정된 변화만으로 생활 상태의 이유를 단정하기는 어려우므로, 평소 모습과 함께 천천히 살펴보는 것이 좋아요. "
        "확인된 내용은 지난주 흐름과 나란히 비교했고, 확인되지 않은 내용으로 해석을 넓히지 않았어요. "
        "크게 서두르기보다는 최근 안부와 생활 리듬을 편안하게 확인해 보시면 다음 흐름을 이해하는 데 도움이 될 수 있어요."
    )
    observations = facts.facts[:3]
    suggestions = [
        action.replace("하기", "해 보셔도 좋아요") for action in facts.suggested_actions[:3]
    ]
    if not suggestions:
        suggestions = ["평소 생활 흐름과 함께 가볍게 살펴보셔도 좋아요."]
    return validate_narrative(
        WeeklyNarrative(
            headline="이번 주 생활 흐름을 차분히 살펴봤어요.",
            analysis_text=analysis,
            observations=observations,
            suggestions=suggestions,
        ),
        facts.allowed_topics,
    )
