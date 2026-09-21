"""Grounded deterministic narrative used when model output cannot be trusted."""

import re

from ax_contracts import WeeklyNarrative

from workflows.weekly_report.domain.models import FactPackage

from .policy import (
    normalize_summary_subscriber_name,
    validate_narrative,
    validate_summary_text,
)


def build_fallback(facts: FactPackage) -> WeeklyNarrative:
    if facts.weekly_report_data is not None:
        try:
            return _build_free_summary_fallback(facts)
        except ValueError:
            # A prose-policy conflict must not discard validated report metrics.
            # This fixed summary makes no claim about the ward or missing data.
            return WeeklyNarrative(
                headline="지난 한 주 생활 정보는 아래 항목에서 확인하실 수 있어요.",
                analysis_text="",
                observations=[],
                suggestions=[],
            )
    selected_facts = facts.facts[:6]
    return validate_narrative(
        WeeklyNarrative(
            headline=_headline(selected_facts),
            analysis_text=_analysis(selected_facts),
            observations=[_formalize(fact) for fact in selected_facts[:3]],
            suggestions=[_suggestion(action) for action in facts.suggested_actions[:3]],
        ),
        facts.allowed_topics,
        facts.required_topics,
        set(),
        False,
    )


def _build_free_summary_fallback(facts: FactPackage) -> WeeklyNarrative:
    data = facts.weekly_report_data
    assert data is not None
    normalized_name = normalize_summary_subscriber_name(data.subscriber)
    name = normalized_name if normalized_name.endswith("님") else f"{normalized_name}님"
    if data.device_status.status == "자료 없음":
        opening = _clean_free_summary_sentence(
            f"지난 한 주 {name}은 생활 정보가 들어오지 않은 날이 있었어요."
        )
        summary = validate_summary_text(
            f"{opening} 기기 전원이 잘 연결되어 있는지 확인해 주세요.",
            facts,
        )
        parts = re.split(r"(?<=[.!?])\s+", summary)
        return WeeklyNarrative(
            headline=parts[0],
            analysis_text=parts[1],
            observations=[],
            suggestions=[],
        )
    activity_pattern = _activity_pattern_observation(facts)
    if activity_pattern:
        opening_activity_pattern = re.sub(
            r"^(?:생활\s+)?활동은",
            "활동이",
            activity_pattern,
        )
        sentences = [f"지난 한 주 {name}은 {opening_activity_pattern}"]
    else:
        overall = _observation_only(data.overall.description).removeprefix(
            "지난 한 주 "
        )
        sentences = [f"지난 한 주 {name}은 {overall}"]

    environment = _observation_only(data.indoor_environment.description)
    device = _observation_only(data.device_status.description)
    supporting = [
        value
        for value in (device, environment)
        if "자료가 부족" not in value
    ]
    if len(supporting) == 2:
        sentences.append(_connect_observations(*supporting))
    elif supporting:
        sentences.append(supporting[0])

    action = _fallback_action(facts)
    if action and _clean_free_summary_sentence(action) not in {
        _clean_free_summary_sentence(sentence) for sentence in sentences
    }:
        sentences.append(action)

    summary = " ".join(_clean_free_summary_sentence(value) for value in sentences[:4])
    summary = validate_summary_text(summary, facts)
    parts = re.split(r"(?<=[.!?])\s+", summary)
    return WeeklyNarrative(
        headline=parts[0],
        analysis_text=" ".join(parts[1:]),
        observations=[],
        suggestions=[],
    )


def _clean_free_summary_sentence(value: str) -> str:
    sentence = re.sub(r"\d+(?:[.,]\d+)?(?:주 전)?", "", value)
    sentence = sentence.replace("움직임", "생활 활동").replace("리모컨", "TV")
    sentence = sentence.replace("생활 모습이 크게 보여요", "생활 모습이 보여요")
    sentence = re.sub(r"\s+", " ", sentence).strip()
    return sentence if sentence.endswith((".", "!", "?")) else f"{sentence}."


def _observation_only(value: str) -> str:
    """Keep the finding and remove section-local action repetition."""

    return re.split(r"(?<=[.!?])\s+", value.strip(), maxsplit=1)[0]


def _connect_observations(first: str, second: str) -> str:
    """Join two report observations without a section-by-section cadence."""

    first = first.rstrip(".!? ")
    if first.endswith("이에요"):
        connected = f"{first.removesuffix('이에요')}이고"
    elif first.endswith("예요"):
        connected = f"{first.removesuffix('예요')}이고"
    elif first.endswith("어요"):
        connected = f"{first.removesuffix('어요')}고"
    else:
        connected = f"{first}이고"
    return f"{connected}, {second}"


def _activity_pattern_observation(facts: FactPackage) -> str | None:
    data = facts.weekly_report_data
    assert data is not None
    activity = data.living_activity.summary
    pattern = data.living_pattern.summary
    unavailable = {None, "비교 자료 없음", "자료 없음", "판정 불가"}
    if activity in unavailable and pattern in unavailable:
        return None
    if activity in unavailable:
        return _observation_only(data.living_pattern.description)
    if pattern in unavailable:
        return _observation_only(data.living_activity.description)

    if activity == pattern:
        shared = {
            "평소 수준": "비슷한 수준으로 이어졌어요.",
            "조금 감소": "함께 조금 줄었어요.",
            "조금 증가": "함께 조금 늘었어요.",
            "많이 감소": "함께 많이 줄었어요.",
            "많이 증가": "함께 많이 늘었어요.",
        }.get(activity)
        if shared:
            return f"생활 활동과 TV 이용 등 일상적인 생활 패턴이 {shared}"

    middle = {
        "평소 수준": "비슷했고",
        "조금 감소": "조금 줄었고",
        "조금 증가": "조금 늘었고",
        "많이 감소": "많이 줄었고",
        "많이 증가": "많이 늘었고",
    }.get(activity)
    ending = {
        "평소 수준": "비슷하게 이어졌어요.",
        "조금 감소": "조금 줄었어요.",
        "조금 증가": "조금 늘었어요.",
        "많이 감소": "많이 줄었어요.",
        "많이 증가": "많이 늘었어요.",
    }.get(pattern)
    if middle and ending:
        return (
            f"생활 활동은 {middle}, TV 이용 등 일상적인 생활 패턴은 {ending}"
        )
    return None


def _fallback_action(facts: FactPackage) -> str | None:
    data = facts.weekly_report_data
    assert data is not None
    for section in (
        data.device_status,
        data.living_activity,
        data.living_pattern,
        data.indoor_environment,
    ):
        if section.status not in {"CAUTION", "RISK"}:
            continue
        parts = re.split(r"(?<=[.!?])\s+", section.description.strip())
        action = next((part for part in parts[1:] if "주세요" in part), None)
        if action:
            return action
    overall_parts = re.split(r"(?<=[.!?])\s+", data.overall.description.strip())
    if len(overall_parts) > 1:
        return overall_parts[1]
    # Activity CAUTION descriptions contain an observation but no action.
    # Keep a check-in when no more specific section action was selected,
    # without implying a routine week or depending on an available score.
    if any(
        section.status in {"CAUTION", "RISK"}
        for section in (data.living_activity, data.living_pattern)
    ):
        return "안부를 한 번 확인해 주세요."
    if data.overall.status == "GOOD":
        return "평소처럼 안부를 확인해 주세요."
    return None


def _sentence(value: str) -> str:
    stripped = _formalize(value).strip()
    return stripped if stripped.endswith((".", "!", "?")) else f"{stripped}."


def _headline(facts: list[str]) -> str:
    activity = _activity_facts(facts)
    if _both_activity_facts_are_stable(activity):
        return "움직임과 리모컨 사용량은 2주 전과 비슷하게 유지되었습니다."
    if activity:
        important = next(
            (fact for fact in activity if _needs_attention(fact)), activity[0]
        )
        return _sentence(important)
    important = next((fact for fact in facts if _needs_attention(fact)), facts[0])
    return _sentence(important)


def _analysis(facts: list[str]) -> str:
    activity = _activity_facts(facts)
    stable: list[str] = []
    attention: list[str] = []

    reception = [fact for fact in facts if _is_good_reception(fact)]
    stable.extend(_sentence(fact) for fact in reception)

    if _both_activity_facts_are_stable(activity):
        stable.append("움직임과 리모컨 사용량은 2주 전과 비슷하게 유지되었습니다.")
    else:
        for fact in activity:
            target = attention if _needs_attention(fact) else stable
            target.append(_sentence(fact))

    for fact in facts:
        if fact in activity or fact in reception:
            continue
        target = attention if _needs_attention(fact) else stable
        target.append(_sentence(fact))

    if attention and stable:
        attention[0] = f"다만 {attention[0]}"
    return " ".join([*stable, *attention])


def _activity_facts(facts: list[str]) -> list[str]:
    return [fact for fact in facts if "움직임" in fact or "리모컨" in fact]


def _both_activity_facts_are_stable(facts: list[str]) -> bool:
    return any("움직임" in fact and "비슷" in fact for fact in facts) and any(
        "리모컨" in fact and "비슷" in fact for fact in facts
    )


def _is_good_reception(fact: str) -> bool:
    return "데이터가 정상적으로 수집" in fact or "생활 정보가 빠짐없이 잘 들어" in fact


def _needs_attention(fact: str) -> bool:
    markers = (
        "위험",
        "주의",
        "필요",
        "이탈",
        "줄어든",
        "늘어난",
        "많이 줄",
        "크게 늘",
        "반복",
        "불편",
        "기기 전원",
        "기기 위치",
    )
    return any(marker in fact for marker in markers)


def _formalize(value: str) -> str:
    replacements = (
        ("수집되었어요", "수집되었습니다"),
        ("들어왔어요", "들어왔습니다"),
        ("유지됐어요", "유지되었습니다"),
        ("비슷했어요", "비슷하게 유지되었습니다"),
        ("확인됐어요", "확인되었습니다"),
        ("반복됐어요", "반복되었습니다"),
        ("이어졌어요", "이어졌습니다"),
        ("있었어요", "있었습니다"),
        ("보여요", "보였습니다"),
        ("필요해요", "필요합니다"),
        ("권장해요", "권장합니다"),
        ("권해요", "권해 드립니다"),
        ("줄었어요", "줄었습니다"),
        ("늘었어요", "늘었습니다"),
        ("많았어요", "많았습니다"),
        ("부족해요", "부족합니다"),
        ("어려워요", "어렵습니다"),
        ("없어요", "없습니다"),
        ("않아요", "않습니다"),
        ("좋아요", "좋습니다"),
        ("건조해요", "건조합니다"),
        ("습해요", "습합니다"),
        ("더워요", "덥습니다"),
        ("추워요", "춥습니다"),
        ("있어요", "있습니다"),
    )
    result = value.strip()
    for casual, formal in replacements:
        result = result.replace(casual, formal)
    return result


def _suggestion(action: str) -> str:
    stripped = action.strip()
    if stripped.endswith("하기"):
        return f"{stripped[:-2]}해 주세요."
    return stripped
