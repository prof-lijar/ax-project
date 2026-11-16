"""Reviewed birthday fields accept source formatting without losing grounding."""

from types import SimpleNamespace

import pytest

from workflows.ax768 import information_policy as policy
from workflows.ax768.information_sheets import LAYOUTS, roster_changes


def draft(birthday):
    return policy.InformationPlan(
        name="김하늘",
        address="",
        current_phone="",
        birthday=birthday,
        new_phone="",
        guardian=None,
        visit_date="",
        memo="",
        blocked_reason="",
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        ("38. 02. 15", "380215"),
        ("38.2.5.", "380205"),
        ("03. 02. 05", "030205"),
        ("1938. 02. 15", "19380215"),
        ("2000.2.29", "20000229"),
        ("380215", "380215"),
        ("19380215", "19380215"),
        ("1938-02-15", "1938-02-15"),
    ],
)
def test_date_formatting_preserves_year_width_and_leading_zeros(value, expected):
    assert policy.normalize_birthday(value) == expected
    p = draft(value)
    assert p.birthday == value  # evidence remains literal until grounding
    assert policy.grounded_plan(p, f"김하늘 · 생년월일: {value}").birthday == expected


@pytest.mark.parametrize(
    "value",
    [
        "38.13.15",
        "38.02.30",
        "38.00.15",
        "1938.2.29",
        "38. 02. 15 확인 필요",
        "38.02.15 또는 39.02.15",
        "3802150",
        "38.\n02.15",
        "38/02/15",
        "38.2",
    ],
)
def test_invalid_or_ambiguous_dates_rejected(value):
    with pytest.raises(ValueError):
        draft(value)


@pytest.mark.asyncio
async def test_reported_single_field_requires_no_model_or_extra_identity(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Simple complete field must not need model configuration")

    monkeypatch.setattr(policy.OpenAICompatibleSettings, "from_env", forbidden)
    p = await policy.prepare_plan(" 이수교 · 생년월일: 38. 02. 15")
    assert p.name == "이수교" and p.birthday == "380215"
    assert p.address == p.current_phone == p.new_phone == "" and p.guardian is None
    assert roster_changes(p, LAYOUTS["영덕"], 6, {"E6": "380214"}) == [
        (6, "E", "380215", False)
    ]
    assert (
        policy.note_for(p, "2026-11-13")
        == "2026-11-13 [현지관리자 방문] 정보확인/생년월일 380215로 수정"
    )


@pytest.mark.parametrize(
    "message",
    [
        "김하늘 · 생년월일: 38. 02. 15\n이도윤 · 생년월일: 39. 02. 15",
        "김하늘 · 생년월일: 38. 02. 15\n김하늘 · 수정요청 전화번호: 010-0000-2222",
        "김하늘 · 생년월일: 38. 02. 15\n변경하지 마세요",
        "메모: 김하늘 · 생년월일: 38. 02. 15",
    ],
)
def test_fast_path_cannot_drop_other_fields_people_or_instructions(message):
    assert policy.structured_birthday_plan(message) is None


def test_normalization_cannot_bypass_source_grounding():
    with pytest.raises(ValueError):
        policy.grounded_plan(draft("380215"), "김하늘 · 생년월일: 38. 02. 15")
    with pytest.raises(ValueError):
        policy.grounded_plan(draft("39.02.15"), "김하늘 · 생년월일: 38. 02. 15")


@pytest.mark.asyncio
async def test_model_path_grounds_literal_date_then_normalizes(monkeypatch):
    class Model:
        def __init__(self, settings):
            pass

        async def complete_structured(self, *args, **kwargs):
            return SimpleNamespace(
                text=draft("38. 02. 15").model_dump_json(), finish_reason="stop"
            )

    monkeypatch.setattr(policy, "OpenAICompatibleChatModel", Model)
    monkeypatch.setattr(
        policy.OpenAICompatibleSettings,
        "from_env",
        lambda: policy.OpenAICompatibleSettings(
            base_url="http://model.invalid/v1", model="test", api_key="synthetic"
        ),
    )
    p = await policy.prepare_plan("김하늘 · 생년월일: 38. 02. 15\n메모: 생년월일 확인")
    assert p.birthday == "380215"
