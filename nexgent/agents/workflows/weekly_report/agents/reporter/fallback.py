"""Grounded deterministic narrative used when model output cannot be trusted."""

import re

from ax_contracts import WeeklyNarrative

from workflows.weekly_report.domain.models import FactPackage

from .policy import validate_narrative, validate_summary_text


def build_fallback(facts: FactPackage) -> WeeklyNarrative:
    if facts.weekly_report_data is not None:
        return _build_free_summary_fallback(facts)
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
    name = data.subscriber if data.subscriber.endswith("님") else f"{data.subscriber}님"
    overall = data.overall.description.removeprefix("지난 한 주 ")
    sentences = [f"지난 한 주 {name}은 {overall}"]

    activity = data.living_activity.description
    pattern = data.living_pattern.description
    if "자료가 부족" not in activity and "자료가 부족" not in pattern:
        sentences.extend((activity, pattern))
    elif "자료가 부족" not in activity:
        sentences.append(activity)
    elif "자료가 부족" not in pattern:
        sentences.append(pattern)

    environment = data.indoor_environment.description
    device = data.device_status.description
    if "자료가 부족" not in device:
        sentences.append(device)
    if "자료가 부족" not in environment:
        sentences.append(environment)

    summary = " ".join(_clean_free_summary_sentence(value) for value in sentences[:5])
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
    sentence = re.sub(r"\s+", " ", sentence).strip()
    return sentence if sentence.endswith((".", "!", "?")) else f"{sentence}."


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
