"""Deterministic narrative safety and structure validation."""

from __future__ import annotations

import re

from ax_contracts import WeeklyNarrative

FORBIDDEN_PHRASES = (
    "위험합니다",
    "응급",
    "사고가 발생",
    "질병",
    "진단",
    "반드시",
    "확실히",
    "틀림없이",
    "건강 이상",
    "하세요",
    "하십시오",
)

TOPIC_MARKERS = {
    "자료 상태": ("자료가 충분하지", "자료가 부족", "장치 상태", "수집 상태"),
    "출동 요청": ("출동",),
    "위험 감지": ("위험", "감지 기록"),
    "활동": ("활동", "움직임", "리모컨"),
    "수면": ("수면", "잠", "기상", "취침", "밤중", "깨어남"),
    "실내 환경": ("실내 환경", "온도", "습도", "조도"),
}


def validate_narrative(
    narrative: WeeklyNarrative,
    allowed_topics: list[str] | None = None,
    required_topics: list[str] | None = None,
) -> WeeklyNarrative:
    values = [
        narrative.headline,
        narrative.analysis_text,
        *narrative.observations,
        *narrative.suggestions,
    ]
    for value in values:
        if not re.search(r"[가-힣]", value):
            raise ValueError("narrative must contain Korean")
        if re.search(r"\d", value):
            raise ValueError("narrative must not contain digits")
        if any(phrase in value for phrase in FORBIDDEN_PHRASES):
            raise ValueError("narrative contains forbidden categorical language")
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", narrative.analysis_text))
    if sentence_count not in {4, 5, 6}:
        raise ValueError("analysis_text must contain four to six sentences")
    if not 220 <= len(narrative.analysis_text) <= 420:
        raise ValueError("analysis_text must contain 220 to 420 characters")
    if len(narrative.observations) != len(set(narrative.observations)):
        raise ValueError("observations must be unique")
    if len(narrative.suggestions) != len(set(narrative.suggestions)):
        raise ValueError("suggestions must be unique")
    if allowed_topics is not None:
        combined = " ".join(values)
        for topic, markers in TOPIC_MARKERS.items():
            if topic not in allowed_topics and any(marker in combined for marker in markers):
                raise ValueError(f"narrative mentions unsupported topic: {topic}")
    if required_topics:
        for topic in required_topics:
            markers = TOPIC_MARKERS.get(topic, (topic,))
            if not any(marker in narrative.analysis_text for marker in markers):
                raise ValueError(f"narrative omits required topic: {topic}")
    return narrative
