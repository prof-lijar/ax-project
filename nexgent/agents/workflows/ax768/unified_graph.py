"""Resolve identity → roster IMEI → fresh signal → conditional AS completion → member notes."""

import asyncio
import os
from typing import Literal, TypedDict

import httpx
from ax_integrations.ansimk import AnsimkClient, AnsimkError, normalize_ping
from ax_integrations.google_sheets import (
    GoogleSheetsClient,
    SheetsError,
    spreadsheet_id,
)
from ax_integrations.sheets_lookup import close_name, lookup_person
from langgraph.graph import END, START, StateGraph

from workflows.ax768.as_update import complete_as_row
from workflows.ax768.city_search import USER_SHEETS
from workflows.ax768.graph import auth_settings, person_sheets_client
from workflows.ax768.imei_case import IMEI_COLUMNS, read_roster_imei
from workflows.ax768.request_parser import compact_name, parse_request
from workflows.ax768.workflow_member_note import (
    member_gate,
    member_note_node,
    requested_action,
    signal_verified,
)


class WorkflowState(TypedDict, total=False):
    workflow_version: Literal["5"]
    message: str
    confirmed_name: str | None
    status: str
    response: str
    parsed: dict
    roster: dict
    as_lookup: dict
    as_update: dict
    member_note: dict | None
    signal: dict
    attempts: list[dict]
    candidates: list[dict]
    notices: list[str]


def receipt(result, *, spreadsheet, alias, city=None):
    row = result.get("row")
    return {
        "status": result["status"],
        "sheet_alias": alias,
        "city": city,
        "sheet_title": result.get("sheet_title"),
        "sheet_id": result.get("sheet_id"),
        "spreadsheet_id": spreadsheet,
        "row": row,
        "name": result.get("name"),
        "address": result.get("address"),
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet}/edit#gid={result['sheet_id']}&range=A{row}"
        if row
        else None,
    }


async def parse_node(state):
    fresh = {
        "parsed": {},
        "member_note": None,
        "roster": {"status": "skipped"},
        "as_lookup": {"status": "skipped"},
        "as_update": {
            "status": "skipped",
            "row": None,
            "date": None,
            "changes": [],
            "y_action": None,
            "verified": False,
            "reason": "기기 연결 확인 전에는 AS시트를 변경하지 않습니다.",
        },
        "signal": {
            "status": "skipped",
            "reason": "가입자 IMEI 확인 후 신호를 조회합니다.",
        },
        "attempts": [],
        "candidates": [],
        "notices": [],
        "response": "",
    }
    try:
        parsed = parse_request(state.get("message"))
        if state.get("workflow_version", "5") != "5":
            raise ValueError("워크플로 버전을 확인해 주세요.")
        requested_action(state["message"])
        confirmed = state.get("confirmed_name")
        if confirmed is not None:
            if not isinstance(confirmed, str) or not parsed["address"]:
                raise ValueError("주소로 확인한 이름 후보를 선택해 주세요.")
            confirmed = compact_name(confirmed)
            if not close_name(parsed["name"], confirmed):
                raise ValueError(
                    "확인한 이름이 원래 요청의 이름 후보와 일치하지 않습니다."
                )
        parsed["lookup_name"] = confirmed or parsed["name"]
        notices = []
        if confirmed:
            notices.append(f"사용자가 확인한 이름: {parsed['name']} → {confirmed}")
        return {**fresh, "parsed": parsed, "notices": notices, "status": "running"}
    except ValueError as exc:
        return {
            **fresh,
            "status": "blocked",
            "response": str(exc),
            "roster": {"status": "skipped"},
            "as_lookup": {"status": "skipped"},
        }


async def roster_node(state):
    parsed = state["parsed"]
    attempts, candidates = [], []
    truncated = False
    current = None
    try:
        provider, key = auth_settings()
        token = provider(os.environ[key])
        async with asyncio.timeout(100), httpx.AsyncClient(timeout=30) as http:
            for target in USER_SHEETS:
                current = target
                sheets = GoogleSheetsClient(target.spreadsheet_id, token, client=http)
                result = await lookup_person(
                    sheets,
                    sheet_id=target.sheet_id,
                    name=parsed["lookup_name"],
                    address=parsed["address"],
                    name_column=target.name_column,
                    address_column=target.address_column,
                    start_row=target.start_row,
                    suggest_names=parsed["mode"] != "name_only"
                    and not bool(state.get("confirmed_name")),
                )
                attempts.append(
                    {
                        "sheet_alias": target.alias,
                        "city": target.city,
                        "status": result["status"],
                    }
                )
                if result["status"] == "found":
                    return {
                        "roster": receipt(
                            result,
                            spreadsheet=target.spreadsheet_id,
                            alias=target.alias,
                            city=target.city,
                        ),
                        "attempts": attempts,
                    }
                for candidate in result["candidates"]:
                    if len(candidates) < 10:
                        candidates.append(
                            receipt(
                                {**result, **candidate, "status": "candidate"},
                                spreadsheet=target.spreadsheet_id,
                                alias=target.alias,
                                city=target.city,
                            )
                        )
                    else:
                        truncated = True
                truncated = truncated or result.get("candidates_truncated", False)
            if len(candidates) == 1 and not truncated:
                candidate = candidates[0]
                current = next(
                    t for t in USER_SHEETS if t.alias == candidate["sheet_alias"]
                )
                # Re-read the selected name/address before handing the corrected name to AS.
                result = await lookup_person(
                    GoogleSheetsClient(current.spreadsheet_id, token, client=http),
                    sheet_id=current.sheet_id,
                    name=candidate["name"],
                    address=parsed["address"],
                    name_column=current.name_column,
                    address_column=current.address_column,
                    start_row=current.start_row,
                )
                if result["status"] != "found":
                    raise SheetsError("Suggested match changed during lookup")
                return {
                    "roster": receipt(
                        result,
                        spreadsheet=current.spreadsheet_id,
                        alias=current.alias,
                        city=current.city,
                    ),
                    "parsed": {**parsed, "lookup_name": result["name"]},
                    "attempts": attempts,
                    "notices": [
                        *state.get("notices", []),
                        f"같은 주소의 유일한 유사 이름을 자동 적용했습니다: {parsed['name']} → {result['name']}",
                    ],
                }
    except (SheetsError, ValueError, KeyError, TimeoutError):
        if current:
            attempts.append(
                {"sheet_alias": current.alias, "city": current.city, "status": "failed"}
            )
        return {
            "status": "failed",
            "response": "가입자 명부 조회에 실패하여 다음 시트로 넘어가지 않았습니다. 접근 권한과 연결을 확인해 주세요.",
            "roster": {"status": "failed"},
            "as_lookup": state["as_lookup"],
            "attempts": attempts,
        }
    if candidates:
        return {
            "status": "needs_confirmation",
            "response": "이름이 정확히 일치하지 않습니다. 같은 주소의 이름 후보를 확인해 주세요.",
            "roster": {"status": "needs_confirmation"},
            "as_lookup": state["as_lookup"],
            "attempts": attempts,
            "candidates": candidates,
        }
    return {
        "status": "not_found",
        "response": "울진 → 광명 → 영덕 명부에서 요청과 일치하는 행을 찾지 못했습니다.",
        "roster": {"status": "not_found"},
        "as_lookup": state["as_lookup"],
        "attempts": attempts,
    }


async def as_node(state):
    parsed = state["parsed"]
    try:
        async with asyncio.timeout(45), httpx.AsyncClient(timeout=30) as http:
            sheets = person_sheets_client(http)
            result = await lookup_person(
                sheets,
                sheet_id=sheets.search_sheet_id,
                name=parsed["lookup_name"],
                address=parsed["address"],
                name_column=sheets.person_name_column,
                address_column=sheets.person_address_column,
                start_row=sheets.search_start_row,
            )
        match = receipt(
            result,
            spreadsheet=spreadsheet_id(os.environ["AX768_CASE_2_3_SPREADSHEET"]),
            alias="AS",
            city=state["roster"].get("city"),
        )
        found = result["status"] == "found"
        return {
            "as_lookup": match,
            **(
                {
                    "as_update": {
                        **state["as_update"],
                        "reason": "일치하는 AS 행이 없어 AS 업데이트를 건너뛰었습니다.",
                    }
                }
                if not found
                else {}
            ),
            "status": "running" if found else "not_found",
            "response": f"AS시트 최신 일치 행: {result['row']}행."
            if found
            else signal_message(state)
            + "AS시트에서 일치하는 행을 찾지 못해 변경하지 않았습니다.",
        }
    except (SheetsError, ValueError, KeyError, TimeoutError):
        return {
            "status": "failed",
            "as_lookup": {"status": "failed"},
            "response": signal_message(state)
            + "AS시트 조회에 실패하여 변경하지 않았습니다.",
        }


def signal_message(state):
    signal = state.get("signal", {})
    if signal.get("status") == "connected":
        return f"S/N {signal['sn']} 신호 확인되었습니다.\n"
    if signal.get("status") == "disconnected":
        return f"S/N {signal['sn']} 전원 연결 및 기기위치 확인해주세요.\n"
    return ""


async def address_node(state):
    """Name-only input takes its identity/address from the bottom-most AS match."""
    result = await as_node(state)
    if result["status"] != "running":
        if result["as_lookup"]["status"] == "not_found":
            result["response"] = (
                "AS시트에서 해당 이름을 찾지 못해 주소를 확인할 수 없습니다. "
                "주소를 입력해 주세요. 신호 확인과 AS·일반 사항 업데이트를 건너뛰었습니다."
            )
        return result
    address = result["as_lookup"].get("address")
    if not isinstance(address, str) or not address.strip():
        return {
            **result,
            "status": "blocked",
            "response": "최신 AS 행에 주소가 없어 가입자와 기기를 확인할 수 없습니다. 주소를 입력해 주세요.",
        }
    return {
        **result,
        "parsed": {**state["parsed"], "address": address.strip()},
        "notices": [
            *state.get("notices", []),
            f"이름만 입력되어 AS시트 {result['as_lookup']['row']}행에서 주소를 확인했습니다.",
        ],
    }


async def signal_node(state):
    signal = {"status": "failed"}
    try:
        match = state["roster"]
        target = next(
            (t for t in USER_SHEETS if t.alias == match.get("sheet_alias")), None
        )
        if (
            target is None
            or match.get("status") != "found"
            or match.get("spreadsheet_id") != target.spreadsheet_id
            or match.get("sheet_id") != target.sheet_id
        ):
            raise SheetsError("가입자 명부의 IMEI 조회 대상을 확인하지 못했습니다.")
        signal["imei_column"] = IMEI_COLUMNS[target.alias]
        provider, key = auth_settings()
        async with asyncio.timeout(20), httpx.AsyncClient(timeout=15) as http:
            signal["imei"] = await read_roster_imei(
                GoogleSheetsClient(
                    target.spreadsheet_id, provider(os.environ[key]), client=http
                ),
                target,
                match,
            )
        async with (
            asyncio.timeout(60),
            httpx.AsyncClient(timeout=55, follow_redirects=False) as http,
        ):
            ping = await AnsimkClient.from_env(http).ping(signal["imei"])
        # The API adapter already validates this; retain a gate at the write boundary.
        ping = validate_signal(ping, signal["imei"])
        signal.update(
            ping,
            status="connected" if ping["connected"] else "disconnected",
            reason=None,
        )
        if ping["connected"]:
            return {"signal": signal}
        return {
            "signal": signal,
            "status": "disconnected",
            "response": f"S/N {ping['sn']} 전원 연결 및 기기위치 확인해주세요.",
            "as_update": {
                **state["as_update"],
                "reason": "연결되지 않아 AS시트를 변경하지 않았습니다.",
            },
        }
    except (
        SheetsError,
        AnsimkError,
        ValueError,
        KeyError,
        TypeError,
        TimeoutError,
    ) as exc:
        reason = (
            str(exc)
            if isinstance(exc, (SheetsError, AnsimkError))
            else "기기 신호를 확인하지 못했습니다. AS시트는 변경하지 않았습니다."
        )
        return {
            "signal": {**signal, "status": "failed", "reason": reason},
            "status": "failed",
            "response": reason,
        }


def validate_signal(ping, imei):
    # Validate the adapter's normalized payload without discarding signal metadata.
    checked = normalize_ping(
        {
            **ping,
            "signal": {"label": ping.get("signal_label"), "rssi": ping.get("rssi")},
        },
        imei,
    )
    return checked


async def update_node(state):
    if not signal_verified(state):
        return {
            "status": "failed",
            "response": "기기 연결이 확인되지 않아 AS시트를 변경하지 않았습니다.",
        }
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            result = await complete_as_row(
                person_sheets_client(http), state["as_lookup"]
            )
    except (SheetsError, ValueError, KeyError):
        result = {
            "status": "failed",
            "row": state["as_lookup"].get("row"),
            "date": None,
            "changes": [],
            "y_action": None,
            "verified": False,
            "reason": "AS 업데이트 설정을 확인하지 못해 변경 요청을 보내지 않았습니다.",
        }
    completed = result["status"] == "updated" and result["verified"]
    return {
        "as_update": result,
        "status": "running" if completed else "failed",
        "response": signal_message(state)
        + f"AS시트 {result['row']}행 처리완료 및 날짜 저장을 확인했습니다."
        if completed
        else signal_message(state) + result["reason"],
    }


def after_signal(state):
    """2.1 is the gate for both writers, independent of the overall status."""
    if not signal_verified(state):
        return "result"
    return (
        "as_update_step"
        if state["as_lookup"]["status"] == "found"
        else "as_lookup_step"
    )


def after_as_lookup(state):
    if not signal_verified(state):
        return "result"
    if state["as_lookup"]["status"] == "found":
        return "as_update_step"
    # A confirmed missing row is the only AS failure that can bypass the writer.
    return "member_note_step" if member_gate(state) else "result"


async def result_node(state):
    """Every exit preserves receipts and explains dependent steps not executed."""
    result = {}
    cause = state.get("response", "")
    if state["signal"]["status"] == "skipped":
        result["signal"] = {**state["signal"], "reason": cause}
    if not signal_verified(state):
        reason = "신호 확인이 완료되지 않아 AS 반영과 일반 사항 저장을 건너뛰었습니다."
    elif state["as_lookup"]["status"] == "failed":
        reason = "AS 조회에 실패하여 AS 반영과 일반 사항 저장을 건너뛰었습니다."
    elif state["as_update"]["status"] in {"failed", "unknown"}:
        reason = "AS 저장 결과를 확인하지 못해 일반 사항 저장을 건너뛰었습니다."
    else:
        reason = None
    if reason:
        if state["as_lookup"]["status"] == "skipped":
            result["as_lookup"] = {**state["as_lookup"], "reason": reason}
        if state["as_update"]["status"] == "skipped":
            result["as_update"] = {**state["as_update"], "reason": reason}
        result["notices"] = [*state.get("notices", []), reason]
    return result


def create_graph():
    builder = StateGraph(WorkflowState)
    builder.add_node("parse", parse_node)
    builder.add_node("address_from_as", address_node)
    builder.add_node("roster_lookup", roster_node)
    builder.add_node("signal_check", signal_node)
    builder.add_node("as_lookup_step", as_node)
    builder.add_node("as_update_step", update_node)
    builder.add_node("member_note_step", member_note_node)
    builder.add_node("result", result_node)
    builder.add_edge(START, "parse")
    builder.add_conditional_edges(
        "parse",
        lambda s: (
            "result"
            if s["status"] != "running"
            else "address_from_as"
            if s["parsed"]["mode"] == "name_only"
            else "roster_lookup"
        ),
    )
    builder.add_conditional_edges(
        "address_from_as",
        lambda s: "roster_lookup" if s["status"] == "running" else "result",
    )
    builder.add_conditional_edges(
        "roster_lookup",
        lambda s: "signal_check" if s["status"] == "running" else "result",
    )
    builder.add_conditional_edges(
        "signal_check",
        after_signal,
    )
    builder.add_conditional_edges(
        "as_lookup_step",
        after_as_lookup,
    )
    builder.add_conditional_edges(
        "as_update_step",
        lambda s: "member_note_step" if member_gate(s) else "result",
    )
    builder.add_edge("member_note_step", "result")
    builder.add_edge("result", END)
    return builder.compile()


graph = create_graph()
