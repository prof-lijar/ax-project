"""Person → latest roster row → city-specific IMEI → verified signal response."""

import asyncio
import re

import httpx
from ax_integrations.ansimk import AnsimkClient, AnsimkError
from ax_integrations.google_sheets import GoogleSheetsClient, SheetsError
from ax_integrations.sheets_address import normalize_address
from ax_integrations.sheets_highlight import first_value
from ax_integrations.sheets_lookup import lookup_person, normalize_person_name

from workflows.ax768.city_search import USER_SHEETS
from workflows.ax768.request_parser import parse_request

# Verified against the row-4 "단말 IMEI (실데이터)" headers on 2026-11-09.
# The preceding Z/Y/V columns contain S/N, which is not an IMEI.
IMEI_COLUMNS = {"uljin-users": "AA", "yeongdeok-users": "Z", "gwangmyeon-users": "W"}


def imei_value(value):
    if type(value) is float and value.is_integer():
        value = int(value)
    value = str(value).strip()
    if not re.fullmatch(r"[0-9]{15}", value):
        raise SheetsError(
            "선택된 가입자 행의 IMEI가 비어 있거나 15자리 숫자가 아닙니다."
        )
    return value


async def read_roster_imei(sheets, target, match):
    """Recheck a selected roster identity and read only its configured IMEI cell."""
    row = match["row"]
    if type(row) is not int or row < target.start_row:
        raise SheetsError("선택된 가입자 행이 올바르지 않습니다.")
    column = IMEI_COLUMNS[target.alias]
    title = "'" + match["sheet_title"].replace("'", "''") + "'"
    data = await sheets._request(
        "GET",
        "/values:batchGet",
        params={
            "ranges": [
                f"{title}!{target.name_column}{row}",
                f"{title}!{target.address_column}{row}",
                f"{title}!{column}{row}",
            ],
            "valueRenderOption": "UNFORMATTED_VALUE",
        },
    )
    cells = data.get("valueRanges", [])
    if (
        len(cells) != 3
        or normalize_person_name(first_value(cells[0])) != match["name"]
        or normalize_address(first_value(cells[1]))
        != normalize_address(match["address"])
    ):
        raise SheetsError("IMEI 조회 중 가입자 행이 변경되어 신호 확인을 중단했습니다.")
    try:
        return imei_value(first_value(cells[2]))
    except SheetsError as exc:
        raise SheetsError(f"{target.city} {column}{row}: {exc}") from None


async def run_imei_case(message, token_provider):
    parsed = parse_request(message)
    receipt = {
        "name": parsed["name"],
        "query": parsed["address"],
        "status": "not_found",
        "attempts": [],
    }
    current = None
    try:
        async with asyncio.timeout(150), httpx.AsyncClient(timeout=30) as http:
            for target in USER_SHEETS:
                current = target
                sheets = GoogleSheetsClient(
                    target.spreadsheet_id, token_provider, client=http
                )
                match = await lookup_person(
                    sheets,
                    sheet_id=target.sheet_id,
                    name=parsed["name"],
                    address=parsed["address"],
                    name_column=target.name_column,
                    address_column=target.address_column,
                    start_row=target.start_row,
                )
                receipt["attempts"].append(
                    {
                        "sheet_alias": target.alias,
                        "city": target.city,
                        "status": match["status"],
                    }
                )
                if match["status"] != "found":
                    continue
                row = match["row"]
                column = IMEI_COLUMNS[target.alias]
                receipt.update(
                    city=target.city,
                    sheet_alias=target.alias,
                    spreadsheet_id=target.spreadsheet_id,
                    sheet_id=target.sheet_id,
                    sheet_title=match["sheet_title"],
                    selected_row=row,
                    query=match["address"],
                    imei_column=column,
                    match_count=1,
                )
                receipt["imei"] = await read_roster_imei(sheets, target, match)
                break
            else:
                return finished(
                    receipt,
                    "completed",
                    "가입자 명부에서 일치하는 이름을 찾지 못했습니다.",
                )
    except (SheetsError, ValueError, KeyError, TimeoutError) as exc:
        if current and (
            not receipt["attempts"]
            or receipt["attempts"][-1]["sheet_alias"] != current.alias
        ):
            receipt["attempts"].append(
                {"sheet_alias": current.alias, "city": current.city, "status": "failed"}
            )
        receipt["status"] = "failed"
        return finished(
            receipt,
            "failed",
            str(exc)
            if isinstance(exc, SheetsError)
            else "가입자 IMEI 조회에 실패했습니다. 신호 확인을 실행하지 않았습니다.",
        )
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as http:
            ping = await AnsimkClient.from_env(http).ping(receipt["imei"])
        receipt.update(
            ping=ping, status="connected" if ping["connected"] else "disconnected"
        )
        response = (
            f"S/N {ping['sn']} 신호 확인되었습니다."
            if ping["connected"]
            else f"S/N {ping['sn']} 전원 연결 및 기기위치 확인해주세요."
        )
        return finished(receipt, "completed", response)
    except AnsimkError as exc:
        receipt["status"] = "failed"
        return finished(receipt, "failed", str(exc))


def finished(receipt, status, response):
    return {
        "status": status,
        "response": response,
        "observations": [{"tool": "imei_signal_check", "result": receipt}],
        "decision": None,
    }
