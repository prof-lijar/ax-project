"""Update only S/X/Y of the selected AS row, with identity checks and readback."""

import asyncio
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ax_integrations.google_sheets import SheetsError, spreadsheet_id
from ax_integrations.sheets_address import normalize_address
from ax_integrations.sheets_highlight import first_value
from ax_integrations.sheets_lookup import normalize_person_name

COMPLETION_STATUS = "처리완료"
COMPLETION_BY_ISSUE = {
    "기기위치 점검": "위치점검완료",
    "기기전원 연결": "전원연결완료",
}


def korea_today():
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def cell_update(sheet_id, row, column_index, value, *, date_cell=False):
    cell = {"userEnteredValue": {"numberValue" if date_cell else "stringValue": value}}
    fields = "userEnteredValue"
    if date_cell:
        cell["userEnteredFormat"] = {
            "numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}
        }
        fields += ",userEnteredFormat.numberFormat"
    return {
        "updateCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row - 1,
                "endRowIndex": row,
                "startColumnIndex": column_index,
                "endColumnIndex": column_index + 1,
            },
            "rows": [{"values": [cell]}],
            "fields": fields,
        }
    }


async def complete_as_row(client, match):
    """One batch mutation, no retries. Post-dispatch uncertainty is never success."""
    receipt = {
        "status": "failed",
        "row": match.get("row"),
        "date": None,
        "changes": [],
        "y_action": None,
        "verified": False,
        "reason": "",
    }
    dispatched = False
    try:
        async with asyncio.timeout(40):
            row, sheet_id = match.get("row"), match.get("sheet_id")
            if (
                match.get("status") != "found"
                or type(row) is not int
                or row < client.search_start_row
                or sheet_id != client.search_sheet_id
                or spreadsheet_id(match.get("spreadsheet_id", ""))
                != client.base.rsplit("/", 1)[-1]
            ):
                raise SheetsError("AS update target does not match the selected row")
            metadata = await client.metadata()
            tab = next(
                (
                    s["properties"]
                    for s in metadata.get("sheets", [])
                    if s["properties"]["sheetId"] == sheet_id
                ),
                None,
            )
            if (
                not tab
                or row > tab.get("gridProperties", {}).get("rowCount", 0)
                or tab.get("gridProperties", {}).get("columnCount", 0) < 25
            ):
                raise SheetsError("AS update row is outside the configured sheet")
            title = "'" + tab["title"].replace("'", "''") + "'"
            identity_ranges = [
                f"{title}!{client.person_name_column}{row}",
                f"{title}!{client.person_address_column}{row}",
                f"{title}!C{row}",
            ]
            snapshot = await client._request(
                "GET",
                "/values:batchGet",
                params={
                    "ranges": identity_ranges,
                    "valueRenderOption": "FORMATTED_VALUE",
                },
            )
            identity = snapshot.get("valueRanges", [])
            if (
                len(identity) != 3
                or normalize_person_name(first_value(identity[0])) != match["name"]
                or normalize_address(first_value(identity[1]))
                != normalize_address(match["address"])
            ):
                raise SheetsError("AS row changed after lookup")
            issue = unicodedata.normalize("NFC", str(first_value(identity[2]))).strip()
            completion = COMPLETION_BY_ISSUE.get(issue)
            today = korea_today()
            serial = (today - date(1899, 12, 30)).days
            changes = [
                {"column": "S", "value": COMPLETION_STATUS},
                {"column": "X", "value": today.isoformat()},
            ]
            expected = [COMPLETION_STATUS, serial]
            requests = [
                cell_update(sheet_id, row, 18, COMPLETION_STATUS),
                cell_update(sheet_id, row, 23, serial, date_cell=True),
            ]
            if completion:
                changes.append({"column": "Y", "value": completion})
                expected.append(completion)
                requests.append(cell_update(sheet_id, row, 24, completion))
            receipt.update(
                date=today.isoformat(),
                changes=changes,
                y_action="updated" if completion else "unchanged",
            )
            dispatched = True
            await client._request("POST", ":batchUpdate", json={"requests": requests})
            checked = await client._request(
                "GET",
                "/values:batchGet",
                params={
                    "ranges": identity_ranges
                    + [f"{title}!{c['column']}{row}" for c in changes],
                    "valueRenderOption": "UNFORMATTED_VALUE",
                    "dateTimeRenderOption": "SERIAL_NUMBER",
                },
            )
            values = checked.get("valueRanges", [])
            if (
                len(values) != len(identity_ranges) + len(changes)
                or normalize_person_name(first_value(values[0])) != match["name"]
                or normalize_address(first_value(values[1]))
                != normalize_address(match["address"])
                or unicodedata.normalize("NFC", str(first_value(values[2]))).strip()
                != issue
                or [first_value(v) for v in values[3:]] != expected
            ):
                raise SheetsError("AS update readback does not match")
            return {
                **receipt,
                "status": "updated",
                "verified": True,
                "reason": "S/X 업데이트 확인 완료. Y는 C값에 따라 처리했습니다.",
            }
    except (SheetsError, ValueError, KeyError, TypeError, TimeoutError):
        return {
            **receipt,
            "status": "unknown" if dispatched else "failed",
            "reason": "변경 요청 후 저장 결과를 확인하지 못했습니다. 재실행 전에 AS 행을 확인해 주세요."
            if dispatched
            else "AS 행을 다시 확인하지 못해 변경 요청을 보내지 않았습니다.",
        }
