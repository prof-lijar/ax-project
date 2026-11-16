"""Opt-in, synthetic, tool-free checks against the configured local model."""

import os

import pytest

from workflows.ax768.information_policy import prepare_plan

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("AX768_LIVE_INFORMATION_EVAL") != "1",
        reason="Opt-in local model evaluation",
    ),
]


@pytest.mark.parametrize(
    "source,field,expected",
    [
        (
            "이름: 김하늘\n주소: 테스트길 10\n요청사항: 생년월일 030215로 수정",
            "birthday",
            "030215",
        ),
        (
            "이름: 김하늘\n주소: 테스트길 10\n수정요청 전화번호: 010-0000-2222\n요청사항: 전화번호수정요망",
            "new_phone",
            "010-0000-2222",
        ),
    ],
)
async def test_explicit_change(source, field, expected):
    result = await prepare_plan(source)
    assert getattr(result, field) == expected and result.current_phone == ""


async def test_guardian_add_preserves_subscriber_identity():
    result = await prepare_plan(
        "이름: 김하늘\n가입자 전화번호: 010-0000-1111\n요청사항: 며느님 추가\n추가연락처: 010-0000-3333"
    )
    assert result.current_phone == "010-0000-1111" and result.new_phone == ""
    assert result.guardian.mode == "add" and result.guardian.phone == "010-0000-3333"
    assert result.guardian.relationship == "며느님"


@pytest.mark.parametrize(
    "source",
    [
        "이름: 김하늘\n주소: 테스트길 10\n기기위치및전원정상입니다",
        "이름: 김하늘\n요청사항: 생년월일380215로수정\n이름: 이도윤\n요청사항: 전화번호010-0000-2222로수정",
    ],
)
async def test_non_actionable_or_multiple_subscribers_block(source):
    with pytest.raises(ValueError):
        await prepare_plan(source)


async def test_qualified_birthday_and_address_are_one_subscriber_update():
    result = await prepare_plan(
        "김하늘 · 주소: 테스트길 10\n김하늘 · 생년월일: 38. 02. 15"
    )
    assert result.name == "김하늘" and result.address == "테스트길 10"
    assert result.birthday == "380215" and result.new_phone == ""
    assert result.guardian is None
