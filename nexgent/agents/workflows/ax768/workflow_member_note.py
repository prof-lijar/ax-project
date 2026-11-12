"""Replace member general notes after verified signal and optional AS completion."""

import re
from datetime import date

from workflows.ax768.as_update import korea_today
from workflows.ax768.member_note import run_member_note
from workflows.ax768.request_parser import compact_name


def requested_action(message):
    text = compact_name(message)
    actions = [value for value in ("기기위치조정", "전원연결") if value in text]
    if len(actions) > 1:
        raise ValueError("기기위치조정 또는 전원연결 중 한 가지 작업을 입력해 주세요.")
    return actions[0] if actions else None


def note_action(state):
    explicit = requested_action(state["message"])
    if explicit:
        return explicit
    values = {
        change.get("value")
        for change in state["as_update"].get("changes", [])
        if change.get("column") == "Y"
    }
    if values == {"위치점검완료"}:
        return "기기위치조정"
    if values == {"전원연결완료"}:
        return "전원연결"
    raise ValueError(
        "일반 사항에 기록할 작업(기기위치조정 또는 전원연결)을 입력해 주세요."
    )


def signal_verified(state):
    signal = state.get("signal", {})
    return (
        signal.get("status") == "connected"
        and signal.get("connected") is True
        and signal.get("fresh") is True
        and state.get("roster", {}).get("status") == "found"
    )


def member_gate(state):
    update, lookup = (
        state.get("as_update", {}),
        state.get("as_lookup", {}),
    )
    return signal_verified(state) and (
        lookup.get("status") == "found"
        and update.get("status") == "updated"
        and update.get("verified") is True
        and update.get("row") == lookup.get("row")
        or lookup.get("status") == "not_found"
        and update.get("status") == "skipped"
    )


async def member_note_node(state):
    prefix = state.get("response", "")
    if not member_gate(state):
        return {
            "status": "failed",
            "member_note": None,
            "response": prefix + "\n일반 사항 저장 조건이 충족되지 않았습니다.",
        }
    try:
        action = note_action(state)
        day = (
            state["as_update"].get("date")
            if state["as_update"]["status"] == "updated"
            else korea_today().isoformat()
        )
        if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
            raise ValueError("일반 사항에 기록할 처리 날짜를 확인하지 못했습니다.")
        roster = state["roster"]
        name, address = roster.get("name"), roster.get("address")
        if not all(
            isinstance(value, str) and value.strip() and not re.search(r"[\r\n]", value)
            for value in (name, address)
        ):
            raise ValueError(
                "가입자 명부의 이름과 주소를 확인하지 못해 일반 사항을 저장하지 않았습니다."
            )
        note = f"{day} [현지관리자 방문] {action}"
        result = await run_member_note(
            f"이름: {name}\n주소: {address}\n일반 사항: {note}"
        )
    except ValueError as exc:
        return {
            "status": "blocked",
            "member_note": None,
            "response": prefix + "\n" + str(exc),
        }
    receipt = result["observations"][0]["result"]
    verified = (
        receipt["status"] in {"saved", "already_present"}
        and receipt["verified"] is True
    )
    return {
        "member_note": receipt,
        "status": "completed"
        if verified
        else "failed"
        if receipt["status"] in {"failed", "unknown"}
        else "blocked",
        "response": prefix + "\n마스터페이지 일반 사항: " + result["response"],
    }
