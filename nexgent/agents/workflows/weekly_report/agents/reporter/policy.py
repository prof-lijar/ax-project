"""Deterministic narrative safety and structure validation."""

from __future__ import annotations

import re

from ax_contracts import WeeklyNarrative

from workflows.weekly_report.domain.models import FactPackage, WeeklySummaryData

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
    "위험",
    "GOOD",
    "CAUTION",
    "RISK",
)

ALARMING_SUMMARY_WORDS = (
    "위급",
    "긴급",
    "즉시",
    "서둘러",
    "급히",
    "심각",
    "비상",
    "경고",
    "불안",
    "우려",
    "염려",
    "주의",
    "걱정",
    "조심",
    "급격",
    "비정상",
    "징후",
    "사고",
    "크게",
)

SUMMARY_EXCLUDED_MANAGEMENT_MARKERS = (
    "기록",
    "살펴볼 기록",
    "확인할 기록",
    "별도 확인 기록",
    "감지 기록",
    "위험 관리",
)

AWKWARD_SUPPORT_PHRASES = (
    "다정하게",
    "따뜻하게",
    "마음을 담아",
    "세심하게",
    "확인이 필요해요",
    "확인이 필요한 상태",
    "주시기 바랍니다",
    "TV 이용 시간",
    "활동량",
)

UNSUPPORTED_SAFETY_REASSURANCE_PHRASES = (
    "다행히",
    "위험한 상황은 없",
    "위험한 상태는 아니",
    "위험하지 않",
    "안전하",
    "안전했",
    "문제가 없",
    "문제없",
    "이상이 없",
    "이상 없",
    "안심해도",
    "걱정하지 않아도",
)

ATTENTION_CONTRADICTING_CLOSE_PHRASES = (
    "평소처럼 지켜봐",
    "평소처럼 계속 지켜봐",
    "평소처럼 따뜻하게 지켜봐",
    "평소처럼 안부를 확인",
)

GENERIC_SUBSCRIBER_REFERENCES = (
    "가입자님",
    "가입자 님",
    "대상자님",
    "대상자 님",
    "어르신",
    "고객님",
    "고객 님",
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
    if any(
        phrase in summary for phrase in UNSUPPORTED_SAFETY_REASSURANCE_PHRASES
    ):
        raise ValueError("weekly summary contains unsupported safety reassurance")
    if "!" in summary or any(word in summary for word in ALARMING_SUMMARY_WORDS):
        raise ValueError("weekly summary contains alarming wording")
    if any(phrase in summary for phrase in AWKWARD_SUPPORT_PHRASES):
        raise ValueError("weekly summary contains persona-misaligned wording")
    if any(marker in summary for marker in SUMMARY_EXCLUDED_MANAGEMENT_MARKERS):
        raise ValueError("weekly summary mentions excluded risk-management content")
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
    if len(sentences) > 4:
        raise ValueError("weekly summary reads like a choppy section recital")
    normalized_sentences = [
        re.sub(
            r"^(?:다만|또한|이와 함께|한편|그리고)\s+",
            "",
            sentence.rstrip(".!? "),
        )
        for sentence in sentences
    ]
    if len(normalized_sentences) != len(set(normalized_sentences)):
        raise ValueError("weekly summary repeats the same sentence")
    if summary.count("안부") > 1:
        raise ValueError("weekly summary repeats the same action intent")

    data = facts.weekly_report_data
    if data is not None:
        known_name = _known_subscriber_name(data.subscriber)
        if known_name is not None and known_name not in summary:
            raise ValueError("weekly summary omits the known subscriber name")
        if known_name is not None and any(
            reference in summary for reference in GENERIC_SUBSCRIBER_REFERENCES
        ):
            raise ValueError("weekly summary uses a generic subscriber reference")
        if data.device_status.status == "자료 없음":
            _validate_no_reception_summary(summary, sentences)
            return summary

        _validate_opening(sentences[0], known_name, data)

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
        if _has_attention_signal(facts) and any(
            phrase in summary for phrase in ATTENTION_CONTRADICTING_CLOSE_PHRASES
        ):
            raise ValueError("weekly summary uses a contradictory stable close")
        _validate_closing_order(sentences, facts)

    for topic in facts.required_topics:
        markers = {
            "활동": ("활동", "TV 이용", "생활 패턴", "일상생활"),
            "실내 환경": TOPIC_MARKERS["실내 환경"],
            "기기 상태": TOPIC_MARKERS["기기 상태"],
        }.get(topic, TOPIC_MARKERS.get(topic, (topic,)))
        if not any(marker in summary for marker in markers):
            raise ValueError(f"weekly summary omits required topic: {topic}")
    return summary


def _validate_no_reception_summary(summary: str, sentences: list[str]) -> None:
    required = (
        "생활 정보가 들어오지 않은 날이 있었어요",
        "기기 전원이 잘 연결되어 있는지 확인해 주세요",
    )
    if len(sentences) != 2 or not all(phrase in summary for phrase in required):
        raise ValueError("weekly summary must use the no-reception two-sentence copy")
    unrelated = (
        "생활 모습",
        "평소와",
        "전반적인 수신 상태",
        "상태 점수",
        "생활 활동",
        "TV 이용",
        "집 안",
        "살펴볼 기록",
    )
    if any(phrase in summary for phrase in unrelated):
        raise ValueError("weekly summary adds unsupported no-reception assessment")


def _validate_closing_order(
    sentences: list[str],
    facts: FactPackage,
) -> None:
    action_indexes = [
        index for index, sentence in enumerate(sentences) if "주세요" in sentence
    ]
    if len(action_indexes) > 1:
        raise ValueError("weekly summary must consolidate actions in the closing")
    if action_indexes and action_indexes[0] != len(sentences) - 1:
        raise ValueError("weekly summary adds facts after the closing action")
    if (_has_attention_signal(facts) or facts.suggested_actions) and not action_indexes:
        raise ValueError("weekly summary omits a grounded closing action")


def _validate_opening(
    first_sentence: str,
    known_name: str | None,
    data: WeeklySummaryData,
) -> None:
    expected = f"지난 한 주 {known_name}님은" if known_name else "지난 한 주"
    if not first_sentence.startswith(expected):
        raise ValueError("weekly summary must use the required opening format")
    opening_remainder = first_sentence.removeprefix(expected).lstrip()
    repeated_topic_starts = (
        r"(?:일상적인\s+)?(?:생활\s+)?활동은(?:\s|,)",
        r"TV\s+이용(?:\s+등\s+일상적인\s+생활\s+패턴)?은(?:\s|,)",
        r"(?:일상적인\s+)?생활\s+패턴은(?:\s|,)",
    )
    if any(re.match(pattern, opening_remainder) for pattern in repeated_topic_starts):
        raise ValueError("weekly summary opening repeats the topic particle")
    activity_available = data.living_activity.status != "자료 없음"
    pattern_available = data.living_pattern.status != "자료 없음"
    if (activity_available or pattern_available) and not any(
        marker in first_sentence
        for marker in ("활동", "TV 이용", "생활 패턴", "일상생활")
    ):
        raise ValueError("weekly summary opening omits the core lifestyle flow")


def _known_subscriber_name(value: str) -> str | None:
    name = normalize_summary_subscriber_name(value)
    if not name or re.search(r"\d", name) or name.startswith("관리 대상"):
        return None
    return name


def normalize_summary_subscriber_name(value: str) -> str:
    """Normalize presentation-only separators without changing report identity."""

    name = re.sub(r"(?<=\])_+", " ", value.strip())
    return re.sub(r"\s+", " ", name)


def _has_attention_signal(facts: FactPackage) -> bool:
    data = facts.weekly_report_data
    if data is None:
        return False
    return (
        data.overall.status in {"CAUTION", "RISK"}
        or any(
            section.status in {"CAUTION", "RISK"}
            for section in (
                data.living_activity,
                data.living_pattern,
                data.indoor_environment,
                data.device_status,
            )
        )
    )


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
