"""Opt-in real-model regression: synthetic chat OCR, never live customer data."""

import os

import pytest

from workflows.ax768.information_extraction import extract

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("AX768_LIVE_EXTRACTION_EVAL") != "1",
        reason="Requires the configured local model and explicit opt-in",
    ),
]

CHAT = """박민수                    H
H
테스트항길 50-1
김하늘님
노치원 다니기시작했음
기기위치및전원정상 입니다   오전 74
박민수
a          =
re vr rere TEE ey
[
sg 744
63 이서연 책임님
박민수에게 답장
신호가 오지않습니다
노치원 기입완료
오전 745
박민수
이도윤님
010-0000-1111
며느님 추가
010-0000-2222
ㅣ| 010-0000-2222 ‘omoey"""


async def run(text):
    result = await extract(
        {
            "workflow_id": "information_update",
            "extraction_version": "1",
            "sources": [{"text": text}],
        }
    )
    assert result["status"] == "completed", result["error"]
    return result["fields"]


async def test_chat_subjects_noise_and_guardian_contact():
    fields = await run(CHAT)
    values = "\n".join(field["value"] for field in fields)
    for fact in [
        "김하늘",
        "테스트항길 50-1",
        "노치원 다니기시작했음",
        "기기위치및전원정상",
        "신호가 오지않습니다",
        "노치원 기입완료",
        "이도윤",
        "010-0000-1111",
        "며느님 추가",
        "010-0000-2222",
    ]:
        assert fact in values, (fact, fields)
    for noise in [
        "박민수",
        "이서연",
        "H",
        "a          =",
        "re vr rere TEE ey",
        "[",
        "sg 744",
        "오전 74",
        "omoey",
    ]:
        assert noise not in values, (noise, fields)
    for field in fields:
        assert (
            "김하늘" in field["label"]
            or "이도윤" in field["label"]
            or "대상자 미확인" in field["label"]
        ), field
        if "테스트항길" in field["value"]:
            assert "김하늘" in field["label"], field
        if "010-0000-" in field["value"]:
            assert "이도윤" in field["label"], field
        if field["value"] == "010-0000-1111":
            assert "보호자" not in field["label"] and "며느" not in field["label"], (
                field
            )
        if field["value"] == "010-0000-2222":
            assert any(role in field["label"] for role in ("며느", "보호자", "추가")), (
                field
            )
    assert values.count("010-0000-2222") == 1, fields


async def test_noise_only_returns_no_case_fields():
    fields = await run(
        "박민수\nH\na          =\nre vr rere TEE ey\n[\nsg 744\n박민수에게 답장\n오전 745"
    )
    assert fields == []


async def test_latin_identifiers_and_business_times_are_not_filtered():
    fields = await run(
        "가입자: 김하늘\n기기 모델: ABC-H2\nS/N: 00300016\n상태: OFFLINE\n방문 예정: 2026-11-14 오전 7:45\n요청: 전원연결 안내"
    )
    values = "\n".join(field["value"] for field in fields)
    for fact in [
        "김하늘",
        "ABC-H2",
        "00300016",
        "OFFLINE",
        "2026-11-14",
        "오전 7:45",
        "전원연결 안내",
    ]:
        assert fact in values, (fact, fields)


async def test_meaningful_ocr_typo_and_unusual_note_are_preserved():
    fields = await run(
        "대상자: 김하늘\n돌봄 참고: 노치원 다니기시작했음\n연락 조건: 저녁 식사 후 통화 가능"
    )
    values = "\n".join(field["value"] for field in fields)
    assert "노치원 다니기시작했음" in values
    assert "저녁 식사 후 통화 가능" in values


async def test_distinct_labeled_records_survive_chunking():
    lines = [
        f"항목{i:02}: 테스트 정보 {i:02} - 다음 방문 일정 확인 및 보호자 연락 후 안내문 전달 예정입니다."
        for i in range(24)
    ]
    sources = [
        {"text": "\n".join(lines)},
        {
            "text": "가입자: 테스트나래\n반려동물: 테스트고양이\n선호 연락 시간: 오후 3시"
        },
    ]
    result = await extract(
        {
            "workflow_id": "information_update",
            "extraction_version": "1",
            "sources": sources,
        }
    )
    assert result["status"] == "completed", result["error"]
    for index, source in enumerate(sources):
        values = "\n".join(
            field["value"]
            for field in result["fields"]
            if field["source_index"] == index
        )
        for line in source["text"].splitlines():
            assert line.split(":", 1)[1].strip() in values, line
