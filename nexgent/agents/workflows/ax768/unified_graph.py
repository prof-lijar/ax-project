"""Roster → AS lookup → bounded completion update; no model-selected writes."""

import asyncio
import os
from typing import Literal, TypedDict

import httpx
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
from workflows.ax768.request_parser import compact_name, parse_request


class WorkflowState(TypedDict, total=False):
    workflow_version: Literal["3"]
    message: str
    confirmed_name: str | None
    status: str
    response: str
    parsed: dict
    roster: dict
    as_lookup: dict
    as_update: dict
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
        "roster": {"status": "pending"},
        "as_lookup": {"status": "pending"},
        "as_update": {
            "status": "skipped",
            "row": None,
            "date": None,
            "changes": [],
            "y_action": None,
            "verified": False,
            "reason": "AS 일치 행을 찾은 후 업데이트합니다.",
        },
        "attempts": [],
        "candidates": [],
        "notices": [],
        "response": "",
    }
    try:
        parsed = parse_request(state.get("message"))
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
        async with asyncio.timeout(150), httpx.AsyncClient(timeout=30) as http:
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
                    suggest_names=not bool(state.get("confirmed_name")),
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
            "as_lookup": {"status": "skipped"},
            "attempts": attempts,
        }
    if candidates:
        return {
            "status": "needs_confirmation",
            "response": "이름이 정확히 일치하지 않습니다. 같은 주소의 이름 후보를 확인해 주세요.",
            "roster": {"status": "needs_confirmation"},
            "as_lookup": {
                "status": "skipped",
                "reason": "이름 확인 후 AS시트를 검색합니다.",
            },
            "attempts": attempts,
            "candidates": candidates,
        }
    return {
        "status": "not_found",
        "response": "울진 → 광명 → 영덕 명부에서 요청과 일치하는 행을 찾지 못했습니다.",
        "roster": {"status": "not_found"},
        "as_lookup": {
            "status": "skipped",
            "reason": "가입자 명부의 일치 행을 먼저 확인해 주세요.",
        },
        "attempts": attempts,
    }


async def as_node(state):
    parsed = state["parsed"]
    try:
        async with asyncio.timeout(60), httpx.AsyncClient(timeout=30) as http:
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
            "status": "running" if found else "not_found",
            "response": f"AS시트 최신 일치 행: {result['row']}행."
            if found
            else "AS시트에서 일치하는 행을 찾지 못했습니다.",
        }
    except (SheetsError, ValueError, KeyError, TimeoutError):
        return {
            "status": "failed",
            "as_lookup": {"status": "failed"},
            "response": "AS시트 조회에 실패했습니다. 앞서 찾은 가입자 명부 결과는 아래에서 확인할 수 있습니다.",
        }


async def update_node(state):
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
        "status": "completed" if completed else "failed",
        "response": f"AS시트 {result['row']}행 처리완료 및 날짜 저장을 확인했습니다."
        if completed
        else result["reason"],
    }


def create_graph():
    builder = StateGraph(WorkflowState)
    builder.add_node("parse", parse_node)
    builder.add_node("roster_lookup", roster_node)
    builder.add_node("as_lookup_step", as_node)
    builder.add_node("as_update_step", update_node)
    builder.add_edge(START, "parse")
    builder.add_conditional_edges(
        "parse", lambda s: "roster_lookup" if s["status"] == "running" else END
    )
    builder.add_conditional_edges(
        "roster_lookup", lambda s: "as_lookup_step" if s["status"] == "running" else END
    )
    builder.add_conditional_edges(
        "as_lookup_step",
        lambda s: "as_update_step" if s["status"] == "running" else END,
    )
    builder.add_edge("as_update_step", END)
    return builder.compile()


graph = create_graph()
