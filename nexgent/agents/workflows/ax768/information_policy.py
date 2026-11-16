"""Source-grounded change intent; identity and write policy are deterministic."""

import re
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Literal

from ax_integrations.chat import OpenAICompatibleChatModel, OpenAICompatibleSettings
from pydantic import Field, model_validator

from .information_extraction import StrictModel


def normalize_birthday(value):
    """Validate the whole date, preserving year width and existing canonical forms."""
    dotted = re.fullmatch(
        r"([0-9]{2}|[0-9]{4})[ \t]*\.[ \t]*([0-9]{1,2})[ \t]*\.[ \t]*([0-9]{1,2})\.?",
        value,
    )
    if dotted:
        year, month, day = dotted.groups()
        normalized = f"{year}{int(month):02}{int(day):02}"
    elif re.fullmatch(r"[0-9]{6}|[0-9]{8}|[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        normalized = value
    else:
        raise ValueError("생년월일 형식을 확인해 주세요. 예: 380215, 38. 02. 15")
    digits = normalized.replace("-", "")
    date(
        int(digits[:4]) if len(digits) == 8 else 2000 + int(digits[:2]),
        int(digits[-4:-2]),
        int(digits[-2:]),
    )
    return normalized


class GuardianChange(StrictModel):
    mode: Literal["add", "replace"]
    current_phone: str = Field(max_length=30)
    name: str = Field(max_length=100)
    relationship: str = Field(max_length=50)
    phone: str = Field(min_length=1, max_length=30)


class InformationPlan(StrictModel):
    name: str = Field(max_length=100)
    address: str = Field(max_length=500)
    current_phone: str = Field(max_length=30)
    birthday: str = Field(max_length=32)
    new_phone: str = Field(max_length=30)
    guardian: GuardianChange | None
    visit_date: str = Field(max_length=10)
    memo: str = Field(max_length=240)
    blocked_reason: str = Field(max_length=300)

    @model_validator(mode="after")
    def formats(self):
        for value in (
            self.current_phone,
            self.new_phone,
            self.guardian.phone if self.guardian else "",
            self.guardian.current_phone if self.guardian else "",
        ):
            if value and not valid_phone(value):
                raise ValueError("전화번호 형식을 확인해 주세요.")
        if self.birthday:
            # Keep literal source evidence until grounded_plan has checked it.
            normalize_birthday(self.birthday)
        if self.visit_date:
            date.fromisoformat(self.visit_date)
        return self


def phone(value):
    return re.sub(r"[^0-9]", "", value)


def valid_phone(value):
    return bool(re.fullmatch(r"[0-9() +.-]+", value)) and bool(
        re.fullmatch(r"0\d{8,10}", phone(value))
    )


def grounded_plan(plan, source):
    if plan.blocked_reason:
        raise ValueError(plan.blocked_reason)
    if not plan.name.strip() or not (plan.birthday or plan.new_phone or plan.guardian):
        raise ValueError(
            "대상자 이름과 수정할 생년월일·전화번호·보호자 정보를 입력해 주세요."
        )
    values = [
        plan.name,
        plan.address,
        plan.current_phone,
        plan.birthday,
        plan.new_phone,
        plan.visit_date,
        plan.memo,
    ]
    if plan.guardian:
        values += [
            plan.guardian.name,
            plan.guardian.relationship,
            plan.guardian.phone,
            plan.guardian.current_phone,
        ]
        if plan.guardian.mode == "replace" and not plan.guardian.current_phone:
            raise ValueError("교체할 기존 보호자 전화번호를 입력해 주세요.")
    if any(
        value and (value not in source or "\n" in value or "\r" in value)
        for value in values
    ):
        raise ValueError("수정 정보가 원문과 일치하지 않습니다. 요청을 확인해 주세요.")
    # An updated contact cannot simultaneously be used to establish old identity.
    if plan.new_phone and phone(plan.new_phone) == phone(plan.current_phone):
        raise ValueError("기존 가입자 번호와 수정할 새 번호를 구분해 주세요.")
    if plan.guardian and phone(plan.guardian.phone) == phone(plan.current_phone):
        raise ValueError("가입자 번호와 보호자 번호를 구분해 주세요.")
    return plan.model_copy(
        update={"birthday": normalize_birthday(plan.birthday) if plan.birthday else ""}
    )


def structured_birthday_plan(message):
    # Consume the ENTIRE request: never silently drop another person's fields,
    # additional requested edits, instructions, or uncertainty markers.
    match = re.fullmatch(
        r"[ \t]*(?P<name>[가-힣A-Za-z][가-힣A-Za-z \t'-]{0,99}?)[ \t]*·[ \t]*"
        r"생년월일[ \t]*[:：][ \t]*(?P<birthday>[^\r\n]+?)[ \t]*",
        message.strip(),
    )
    if not match:
        return None
    plan = InformationPlan(
        name=match["name"].strip(),
        address="",
        current_phone="",
        birthday=match["birthday"],
        new_phone="",
        guardian=None,
        visit_date="",
        memo="",
        blocked_reason="",
    )
    return grounded_plan(plan, message)


async def prepare_plan(message):
    if not message.strip() or len(message) > 8000:
        raise ValueError("한 가입자의 요청을 8,000자 이내로 입력해 주세요.")
    structured = structured_birthday_plan(message)
    if structured is not None:
        return structured
    model = OpenAICompatibleChatModel(
        replace(OpenAICompatibleSettings.from_env(), max_attempts=1, timeout_seconds=90)
    )
    completion = await model.complete_structured(
        [
            {
                "role": "system",
                "content": Path(__file__)
                .with_name("prompts")
                .joinpath("information_update.md")
                .read_text(),
            },
            {"role": "user", "content": message},
        ],
        response_schema=InformationPlan.model_json_schema(),
        schema_name="ax768_information_update",
        max_tokens=1800,
        temperature=0,
    )
    if completion.finish_reason != "stop":
        raise ValueError("수정 요청 분석이 완료되지 않았습니다.")
    return grounded_plan(InformationPlan.model_validate_json(completion.text), message)


def note_for(plan, today):
    edits = []
    if plan.birthday:
        edits.append(f"생년월일 {plan.birthday}로 수정")
    if plan.new_phone:
        edits.append(f"가입자 전화번호 {plan.new_phone}로 수정")
    if plan.guardian:
        g = plan.guardian
        edits.append(
            "보호자 "
            + " ".join(filter(None, [g.name, g.relationship, g.phone]))
            + (" 추가" if g.mode == "add" else "로 수정")
        )
    return (
        f"{plan.visit_date or today} [현지관리자 방문] 정보확인/"
        + ", ".join(edits)
        + (f" ({plan.memo})" if plan.memo else "")
    )
