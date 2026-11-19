"""Identify one member and verify a replacement or workflow-only appended note."""

import asyncio
import re
import unicodedata
from datetime import date

import httpx
from ax_integrations.ansimk_members import (
    AnsimkMembersClient,
    MembersError,
    MembersRejected,
)

from workflows.ax768.member_address import member_address_matches


def compact(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def parse_member_note(message):
    fields = {}
    for line in message.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(
            r"\s*(이름|주소|가입자 ID|일반\s*사항)\s*[:：]\s*(.*?)\s*", line
        )
        if not match:
            raise ValueError(
                "이름: 가입자명 / 일반 사항: 날짜와 내용을 각각 한 줄로 입력해 주세요."
            )
        key = compact(match[1])
        if key in fields:
            raise ValueError("한 번에 한 가입자의 메모만 입력해 주세요.")
        fields[key] = match[2]
    name, note = fields.get("이름", ""), fields.get("일반사항", "")
    if (
        not name
        or len(name) > 100
        or not re.fullmatch(r"[가-힣A-Za-z0-9_() .·-]+", name)
    ):
        raise ValueError("가입자 이름을 확인해 주세요.")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \S.*", note) or len(note) > 500:
        raise ValueError(
            "일반 사항은 YYYY-MM-DD로 시작하는 500자 이내의 한 줄로 입력해 주세요."
        )
    try:
        date.fromisoformat(note[:10])
    except ValueError:
        raise ValueError("일반 사항의 날짜를 확인해 주세요.") from None
    member_id = fields.get("가입자ID", "")
    if member_id and (
        not member_id.isascii()
        or not member_id.isdigit()
        or not 0 < int(member_id) < 2**53
    ):
        raise ValueError("가입자 ID는 양의 정수여야 합니다.")
    address = fields.get("주소", "")
    if len(address) > 500:
        raise ValueError("주소는 500자 이내로 입력해 주세요.")
    return {
        "name": name,
        "note": note,
        "address": address,
        "member_id": int(member_id) if member_id else None,
    }


def identity(row):
    name, address = row.get("full_name"), row.get("address") or ""
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 100
        or not isinstance(address, str)
        or len(address) > 1000
    ):
        raise MembersError("가입자 이름과 주소를 확인하지 못했습니다.")
    return {"member_id": row["id"], "name": name, "address": address}


def notes_of(row):
    value = row.get("general_notes")
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > 2000:
        raise MembersError("기존 일반 사항의 형식 또는 길이를 확인해 주세요.")
    return value


async def run_member_note(message, *, placement="replace", region=None):
    parsed = parse_member_note(message)
    if placement not in {"replace", "append", "prepend"}:
        raise ValueError("지원하지 않는 메모 기록 방식입니다.")
    preserve_history = placement != "replace"
    if preserve_history and not parsed["address"]:
        raise ValueError(
            "기존 일반 사항에 추가하려면 대상자의 이름과 주소가 모두 필요합니다."
        )
    receipt = {
        "status": "failed",
        "member_id": None,
        "name": parsed["name"],
        "address": parsed["address"],
        "note": parsed["note"],
        "verified": False,
        "candidates": [],
    }
    dispatched = False

    def output(status, response):
        return {
            "status": status,
            "response": response,
            "observations": [{"tool": "member_general_note", "result": receipt.copy()}],
        }

    try:
        async with (
            asyncio.timeout(120),
            httpx.AsyncClient(timeout=20, follow_redirects=False) as http,
        ):
            client = AnsimkMembersClient.from_env(http)
            await client.login()
            rows = [identity(row) for row in await client.search(parsed["name"])]
            eligible = [
                row
                for row in rows
                if compact(parsed["name"]) in compact(row["name"])
                and (
                    not parsed["address"]
                    or (
                        member_address_matches(
                            parsed["address"], row["address"], region
                        )
                        if region is not None
                        else compact(row["address"]) == compact(parsed["address"])
                    )
                )
                and (not parsed["member_id"] or row["member_id"] == parsed["member_id"])
            ]
            exact = [
                row
                for row in eligible
                if compact(row["name"]) == compact(parsed["name"])
            ]
            candidates = exact or eligible
            if len(candidates) != 1:
                receipt.update(
                    status="needs_confirmation" if candidates else "not_found",
                    candidates=candidates[:20],
                )
                return output(
                    "blocked" if candidates else "completed",
                    "일치하는 가입자가 여러 명입니다. 대상 가입자를 선택한 뒤 다시 실행해 주세요."
                    if candidates
                    else "이름과 조건에 일치하는 가입자가 없어 저장하지 않았습니다.",
                )
            selected = candidates[0]
            receipt.update(selected)
            before = await client.detail(selected["member_id"])
            if identity(before) != selected:
                raise MembersError(
                    "가입자 이름 또는 주소가 변경되어 저장하지 않았습니다."
                )
            old = notes_of(before)
            already_present = (
                any(line.strip() == parsed["note"] for line in old.splitlines())
                if preserve_history
                else parsed["note"] == old
            )
            if already_present:
                receipt.update(status="already_present", verified=True)
                return output(
                    "completed",
                    "동일한 기록이 일반 사항에 이미 있어 추가하지 않았습니다."
                    if preserve_history
                    else "일반 사항이 입력 내용과 같아 변경하지 않았습니다.",
                )
            if preserve_history:
                separator = (
                    ""
                    if not old or old.endswith(("\n", "\r"))
                    else "\r\n"
                    if "\r\n" in old
                    else "\n"
                )
                desired = (
                    parsed["note"]
                    + (("\r\n" if "\r\n" in old else "\n") if old else "")
                    + old
                    if placement == "prepend"
                    else old + separator + parsed["note"]
                )
                if len(desired) > 2000:
                    raise MembersError(
                        "기존 일반 사항을 보존하고 추가하면 2,000자를 초과하여 저장하지 않았습니다."
                    )
            else:
                desired = parsed["note"]
            fresh = await client.detail(selected["member_id"])
            if identity(fresh) != selected or notes_of(fresh) != old:
                raise MembersError(
                    "저장 직전에 가입자 정보 또는 일반 사항이 변경되어 중단했습니다."
                )
            dispatched = True
            try:
                await client.write_notes(selected["member_id"], desired)
            except MembersRejected:
                dispatched = False
                raise
            after = await client.detail(selected["member_id"])
            if identity(after) != selected or notes_of(after) != desired:
                raise MembersError("저장 후 일반 사항이 예상 내용과 일치하지 않습니다.")
            receipt.update(status="saved", verified=True)
            return output(
                "completed",
                f"{selected['name']}님의 일반 사항 {'첫' if placement == 'prepend' else '마지막'} 줄에 기록을 추가하고 저장을 확인했습니다.\n{parsed['note']}"
                if preserve_history
                else f"{selected['name']}님의 일반 사항을 입력 내용으로 교체하고 저장을 확인했습니다.\n{parsed['note']}",
            )
    except (MembersError, TimeoutError) as exc:
        receipt["status"] = "unknown" if dispatched else "failed"
        reason = (
            str(exc)
            if isinstance(exc, MembersError)
            else "가입자 관리 처리 시간이 초과되었습니다."
        )
        return output(
            "failed",
            reason
            + (
                " 저장되었을 수 있으므로 재실행 전에 일반 사항을 확인해 주세요."
                if dispatched
                else " 변경을 확인하지 못했으며 추가 저장 요청을 보내지 않았습니다."
            ),
        )
