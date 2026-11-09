"""Explicit workflow cases; IDs are strings so 1.10 stays distinct from 1.1."""

import re
import unicodedata

from ax_contracts.sheets import (
    SearchAddress,
    SearchName,
    SearchPersonRow,
    SearchUserSheets,
)

from workflows.ax768.request_parser import parse_request
from workflows.ax768.signal_check import requested_name

CASE_DESCRIPTIONS = {
    "imei": "IMEI case: find a roster IMEI and check its device signal",
    "1.1": "Find a person's latest matching name row",
    "2.2": "Find an address and return the bottom-most matching row",
    "2.3": "Find the latest AS row matching address and name",
    "4.2": "Search user sheets in order by address and name; return city and latest row",
    "4.3": "Find the latest AS name/address row from a signal-check request",
    "6.2": "Find a user across city rosters from address,name,request text",
    "6.3": "Find the latest AS row from address,name,request text",
}


def case_action(case_id: str | None, message: str):
    if case_id is None:
        return None
    if not isinstance(case_id, str) or case_id not in CASE_DESCRIPTIONS:
        raise ValueError(
            f"Unknown AX768 case: {case_id}. Available cases: {', '.join(CASE_DESCRIPTIONS)}"
        )
    if case_id == "imei":
        parse_request(message)
        return None
    if case_id in {"6.2", "6.3"}:
        parts = [
            part.strip() for part in unicodedata.normalize("NFC", message).split(",", 2)
        ]
        if len(parts) != 3 or not all(parts):
            raise ValueError(
                f'Case {case_id} expects "주소,이름,요청내용", e.g. "왕피길83-15,정영자,기기위치조정 수신확인요~"'
            )
        address, name, _request_text = parts
        name = name.removesuffix("님").strip()
        if not re.fullmatch(r"[가-힣]{2,10}", name) or not re.search(r"\d", address):
            raise ValueError(
                f"Case {case_id} requires an address with a number and a Korean name"
            )
        if case_id == "6.3":
            return SearchPersonRow(tool="search_person_row", name=name, address=address)
        return SearchUserSheets(tool="search_user_sheets", name=name, address=address)
    if case_id in {"2.3", "4.2", "4.3"}:
        text = unicodedata.normalize("NFC", message).strip()
        if case_id in {"4.2", "4.3"}:
            text = re.sub(
                r"님\s*신호\s*확인\s*(?:요|해주세요|해\s*주세요|부탁드립니다)?[.!?。]*\s*$",
                "",
                text,
            ).strip()
        parts = text.rsplit(maxsplit=1)
        if (
            len(parts) != 2
            or not re.fullmatch(r"[가-힣]{2,10}", parts[-1])
            or not re.search(r"\d", parts[0])
            or (case_id in {"4.2", "4.3"} and re.search(r"[가-힣]님(?:\s|$)", text))
        ):
            raise ValueError(
                f'Case {case_id} expects address then name, e.g. "후포로 158 김동명"'
            )
        if case_id == "4.2":
            return SearchUserSheets(
                tool="search_user_sheets", address=parts[0], name=parts[1]
            )
        return SearchPersonRow(
            tool="search_person_row", address=parts[0], name=parts[1]
        )
    if case_id == "2.2":
        return SearchAddress(tool="search_address", address=message.strip())
    name = requested_name(message)
    if name is None:
        raise ValueError('Case 1.1 expects a request such as "김순옥님 신호확인요."')
    return SearchName(tool="search_name", name=name)
