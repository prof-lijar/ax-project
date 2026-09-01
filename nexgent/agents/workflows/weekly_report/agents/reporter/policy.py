"""Deterministic narrative safety and structure validation."""

from __future__ import annotations

import re

from ax_contracts import WeeklyNarrative

from workflows.weekly_report.domain.models import FactPackage

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
    "각 항목을 살펴보면",
    "자료를 바탕으로",
    "종합적으로 확인되었습니다",
    "전반적인 생활 흐름을 안정적으로 확인할 수 있었습니다",
    "첫째",
    "둘째",
    "셋째",
)

LEGACY_REPORT_PERIOD_PHRASES = (
    "이번 주",
    "지난주",
    "지난 주",
)

FORMAL_NARRATIVE_ENDINGS = ("습니다", "입니다", "합니다", "됩니다")

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
    "기기 상태": (
        "데이터가 정상적으로 수집",
        "생활 정보",
        "기기 전원",
        "기기 위치",
        "수신상태",
        "기기 데이터",
    ),
    "활동": ("활동", "움직임", "리모컨"),
    "실내 환경": (
        "실내 환경",
        "온도",
        "습도",
        "조도",
        "집 안",
        "더운",
        "추운",
        "습한",
        "건조한",
        "덥고",
    ),
}

FREE_SUMMARY_FORBIDDEN_WORDS = (
    "움직임",
    "리모컨",
    "GOOD",
    "CAUTION",
    "RISK",
)


def validate_summary_text(text: str, facts: FactPackage) -> str:
    """Validate one model-authored, report-ready summary paragraph."""

    summary = text.strip()
    if not summary:
        raise ValueError("weekly summary must not be empty")
    if "\n" in summary or "\r" in summary:
        raise ValueError("weekly summary must be one paragraph")
    if summary.startswith(("#", "-", "*", ">")) or re.search(
        r"(?:^|\s)(?:제목|총평|설명)\s*:", summary
    ):
        raise ValueError("weekly summary must contain body text only")
    if not re.search(r"[가-힣]", summary):
        raise ValueError("weekly summary must contain Korean")
    if re.search(r"\d", summary):
        raise ValueError("weekly summary must not contain digits")
    if any(word in summary for word in FREE_SUMMARY_FORBIDDEN_WORDS):
        raise ValueError("weekly summary contains a forbidden output word")
    if any(phrase in summary for phrase in FORBIDDEN_PHRASES):
        raise ValueError("weekly summary contains forbidden categorical language")
    if any(phrase in summary for phrase in UNRELATED_FILLER_PHRASES):
        raise ValueError("weekly summary contains unrelated filler")
    if any(phrase in summary for phrase in LEGACY_REPORT_PERIOD_PHRASES):
        raise ValueError("weekly summary contains a legacy report-period phrase")
    if any(marker in summary for marker in REPORT_EXCLUDED_TOPIC_MARKERS):
        raise ValueError("weekly summary mentions a report-excluded topic")
    if any(phrase in summary for phrase in URGENT_NARRATIVE_PHRASES):
        raise ValueError("weekly summary contains urgent wording")
    if any(ending in summary for ending in FORMAL_NARRATIVE_ENDINGS):
        raise ValueError("weekly summary must use warm haeyo register")
    if len(summary) > 500:
        raise ValueError("weekly summary must contain at most 500 characters")

    sentences = re.split(r"(?<=[.!?])\s+", summary)
    if not 1 <= len(sentences) <= 12 or any(
        not sentence.endswith((".", "!", "?")) for sentence in sentences
    ):
        raise ValueError("weekly summary must contain one to twelve sentences")
    if len(sentences[0]) > 160:
        raise ValueError("weekly summary first sentence must contain at most 160 characters")

    data = facts.weekly_report_data
    if data is not None:
        material_markers = (
            (data.living_activity.status, ("활동",), "생활 활동"),
            (
                data.living_pattern.status,
                ("TV 이용", "생활 패턴", "일상생활"),
                "생활 패턴",
            ),
            (
                data.indoor_environment.status,
                TOPIC_MARKERS["실내 환경"],
                "실내 환경",
            ),
            (data.device_status.status, TOPIC_MARKERS["기기 상태"], "기기 상태"),
        )
        for status, markers, label in material_markers:
            if status in {"CAUTION", "RISK"} and not any(
                marker in summary for marker in markers
            ):
                raise ValueError(f"weekly summary omits material section: {label}")

    for topic in facts.required_topics:
        markers = {
            "활동": ("활동", "TV 이용", "생활 패턴", "일상생활"),
            "실내 환경": TOPIC_MARKERS["실내 환경"],
            "기기 상태": TOPIC_MARKERS["기기 상태"],
        }.get(topic, TOPIC_MARKERS.get(topic, (topic,)))
        if not any(marker in summary for marker in markers):
            raise ValueError(f"weekly summary omits required topic: {topic}")
    return summary


def validate_narrative(
    narrative: WeeklyNarrative,
    allowed_topics: list[str] | None = None,
    required_topics: list[str] | None = None,
    allowed_numbers: set[str] | None = None,
    structured_outline: bool = False,
    available_items: list[str] | None = None,
    required_analysis_block: str | None = None,
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
    analysis_remainder = (
        _required_block_remainder(
            narrative.analysis_text,
            required_analysis_block,
        )
        if structured_outline and required_analysis_block
        else narrative.analysis_text
    )
    if structured_outline and any(
        ending in value
        for value in (narrative.headline, analysis_remainder)
        for ending in FORMAL_NARRATIVE_ENDINGS
    ):
        raise ValueError("headline and analysis_text must use warm haeyo register")
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", narrative.analysis_text))
    if (
        structured_outline
        and has_evaluable_items
        and sentence_count not in {1, 2, 3, 4}
    ):
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
        if required_analysis_block:
            _required_block_remainder(
                narrative.analysis_text,
                required_analysis_block,
            )
        _require_supporting_insight(
            narrative.analysis_text,
            required_analysis_block,
            available_items,
        )
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
        "기기 상태": ("기기", "데이터 수신", "전원", "위치"),
    }
    for item, markers in item_markers.items():
        if item not in available and any(marker in text for marker in markers):
            raise ValueError(f"structured summary mentions omitted item: {item}")


def _required_block_remainder(text: str, required_block: str) -> str:
    if text == required_block:
        return ""
    if text.startswith(f"{required_block} "):
        return text[len(required_block) + 1 :]
    for connector in SUMMARY_CONNECTORS:
        prefixed_block = f"{connector} {required_block}"
        if text == prefixed_block:
            return ""
        if text.startswith(f"{prefixed_block} "):
            return text[len(prefixed_block) + 1 :]
    raise ValueError("structured analysis must start with the required activity block")


def _require_supporting_insight(
    text: str,
    required_block: str | None,
    available_items: list[str] | None,
) -> None:
    if not required_block or not available_items:
        return
    has_supporting_evidence = any(
        item in {"실내 환경", "기기 상태"} for item in available_items
    )
    if has_supporting_evidence and not _required_block_remainder(
        text,
        required_block,
    ):
        raise ValueError("structured summary must add a supporting weekly insight")
