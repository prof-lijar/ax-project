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

UNRELATED_FILLER_PHRASES = (
    "생활 요약 안내드립니다",
    "양해 부탁드립니다",
    "너무 염려하지",
    "건강 상태의 변화를 의미하는 것은 아니",
    "다음 주에는",
    "풍성한 기록",
    "정성껏 살펴보고",
    "보호자님께서도 마음 편히",
    "함께 지켜봐 주시기를 부탁드립니다",
)

LEGACY_REPORT_PERIOD_PHRASES = (
    "이번 주",
    "지난주",
    "지난 주",
)

CASUAL_NARRATIVE_ENDINGS = (
    "됐어요",
    "했어요",
    "있어요",
    "보여요",
    "필요해요",
    "권장해요",
    "권해요",
    "없어요",
    "어려워요",
    "이어졌어요",
    "줄었어요",
    "늘었어요",
    "많았어요",
    "않아요",
    "좋아요",
    "건조해요",
    "습해요",
    "더워요",
    "추워요",
)

URGENT_NARRATIVE_PHRASES = (
    "빠른",
    "빠르게",
    "즉시",
    "위급",
    "긴급",
)

SUMMARY_CONNECTORS = (
    "구체적으로",
    "특히",
    "다만",
    "이와 함께",
    "또한",
    "한편",
    "따라서",
    "반면",
)

REPORT_EXCLUDED_TOPIC_MARKERS = (
    "수면",
    "잠",
    "기상",
    "취침",
    "밤중",
    "깨어남",
    "새벽 각성",
    "출동",
)

TOPIC_MARKERS = {
    "자료 상태": (
        "자료가 충분하지",
        "자료가 부족",
        "장치 상태",
        "수집 상태",
        "확인 가능한 주간 자료",
        "유효 데이터",
    ),
    "위험 감지": ("위험", "감지 기록"),
    "기기 데이터 수신": (
        "데이터가 정상적으로 수집",
        "기기 전원",
        "기기 위치",
        "수신상태",
        "기기 데이터",
    ),
    "활동": ("활동", "움직임", "리모컨"),
    "실내 환경": ("실내 환경", "온도", "습도", "조도"),
}


def validate_narrative(
    narrative: WeeklyNarrative,
    allowed_topics: list[str] | None = None,
    required_topics: list[str] | None = None,
    allowed_numbers: set[str] | None = None,
    structured_outline: bool = False,
    available_items: list[str] | None = None,
) -> WeeklyNarrative:
    has_evaluable_items = available_items is None or bool(available_items)
    named_values = [
        ("headline", narrative.headline),
        ("analysis_text", narrative.analysis_text),
        *(("observation", value) for value in narrative.observations),
        *(("suggestion", value) for value in narrative.suggestions),
    ]
    for field_name, value in named_values:
        if (
            field_name == "analysis_text"
            and structured_outline
            and not has_evaluable_items
            and not value
        ):
            continue
        if not re.search(r"[가-힣]", value):
            raise ValueError("narrative must contain Korean")
        number_source = value.replace("2주 전", "")
        numbers = set(re.findall(r"\d+(?:[.,]\d+)?", number_source))
        if numbers - (allowed_numbers or set()):
            raise ValueError("narrative must not contain unsupported digits")
        if any(phrase in value for phrase in FORBIDDEN_PHRASES):
            raise ValueError("narrative contains forbidden categorical language")
        if any(phrase in value for phrase in UNRELATED_FILLER_PHRASES):
            raise ValueError("narrative contains unrelated filler")
        if any(phrase in value for phrase in LEGACY_REPORT_PERIOD_PHRASES):
            raise ValueError("narrative contains a legacy report-period phrase")
        if any(marker in value for marker in REPORT_EXCLUDED_TOPIC_MARKERS):
            raise ValueError("narrative mentions a report-excluded topic")
        if structured_outline and any(
            phrase in value for phrase in URGENT_NARRATIVE_PHRASES
        ):
            raise ValueError("structured summary contains urgent wording")
    if any(
        ending in value
        for value in (narrative.headline, narrative.analysis_text)
        for ending in CASUAL_NARRATIVE_ENDINGS
    ):
        raise ValueError("headline and analysis_text must use formal Korean register")
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", narrative.analysis_text))
    if structured_outline and has_evaluable_items and sentence_count not in {1, 2, 3, 4}:
        raise ValueError("structured analysis_text must contain one to four insights")
    if structured_outline and not has_evaluable_items and sentence_count != 0:
        raise ValueError("structured analysis_text must be empty without insights")
    if not structured_outline and sentence_count not in {1, 2, 3, 4, 5, 6}:
        raise ValueError("analysis_text must contain one to six sentences")
    if structured_outline and bool(narrative.observations) != has_evaluable_items:
        raise ValueError("structured observations must match insight availability")
    if structured_outline:
        if not narrative.headline.startswith("지난 한 주 "):
            raise ValueError("structured headline must start with the report period")
        if "지난 한 주" in narrative.analysis_text:
            raise ValueError("structured analysis repeats the report period")
        _validate_connected_sentences(narrative.analysis_text)
    if len(narrative.analysis_text) > 420:
        raise ValueError("analysis_text must contain at most 420 characters")
    if (
        structured_outline
        and len(narrative.headline) + len(narrative.analysis_text) > 450
    ):
        raise ValueError("structured summary must contain at most 450 characters")
    if structured_outline and any(
        narrative.analysis_text.count(connector) > 2
        for connector in ("다만", "이와 함께", "또한", "한편")
    ):
        raise ValueError("structured summary repeats a connector too often")
    if structured_outline:
        ending_tokens = re.findall(
            r"([가-힣]+)[.!?]",
            f"{narrative.headline} {narrative.analysis_text}",
        )
        if any(ending_tokens.count(token) > 2 for token in set(ending_tokens)):
            raise ValueError("structured summary repeats a sentence ending too often")
        _reject_omitted_items(
            " ".join(value for _, value in named_values), available_items
        )
    if len(narrative.observations) != len(set(narrative.observations)):
        raise ValueError("observations must be unique")
    if len(narrative.suggestions) != len(set(narrative.suggestions)):
        raise ValueError("suggestions must be unique")
    if allowed_topics is not None:
        combined = " ".join(value for _, value in named_values)
        for topic, markers in TOPIC_MARKERS.items():
            if topic not in allowed_topics and any(
                marker in combined for marker in markers
            ):
                raise ValueError(f"narrative mentions unsupported topic: {topic}")
    if required_topics:
        for topic in required_topics:
            markers = TOPIC_MARKERS.get(topic, (topic,))
            if not any(marker in narrative.analysis_text for marker in markers):
                raise ValueError(f"narrative omits required topic: {topic}")
    return narrative


def _reject_omitted_items(text: str, available_items: list[str] | None) -> None:
    if available_items is None:
        return
    available = set(available_items)
    item_markers = {
        "움직임": ("움직임",),
        "리모컨": ("리모컨",),
        "실내 환경": ("실내 환경", "온도", "습도"),
        "기기 데이터 수신": ("기기", "데이터 수신", "전원", "위치"),
    }
    for item, markers in item_markers.items():
        if item not in available and any(marker in text for marker in markers):
            raise ValueError(f"structured summary mentions omitted item: {item}")


def _validate_connected_sentences(text: str) -> None:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text.strip())
        if sentence.strip()
    ]
    for sentence in sentences:
        if not sentence.startswith(SUMMARY_CONNECTORS):
            raise ValueError("structured summary sentences must use connectors")
