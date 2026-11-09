"""Only the selected AS row's S/X/Y may change; uncertain writes never retry."""

import json
from datetime import UTC, date, datetime

import httpx
import pytest
from ax_integrations.google_sheets import GoogleSheetsClient

from workflows.ax768 import as_update


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "issue,expected_y",
    [
        ("기기위치 점검", "위치점검완료"),
        ("기기전원 연결", "전원연결완료"),
        (" 다른 유형 ", None),
        ("", None),
    ],
)
@pytest.mark.parametrize(
    "failure",
    [
        None,
        "changed_name",
        "changed_address",
        "out_of_bounds",
        "wrong_target",
        "write_timeout",
        "readback_error",
        "wrong_value",
        "changed_issue",
    ],
)
async def test_bounded_write_and_verification(monkeypatch, issue, expected_y, failure):
    monkeypatch.setattr(as_update, "korea_today", lambda: date(2026, 11, 4))
    serial = (date(2026, 11, 4) - date(1899, 12, 30)).days
    posts = []
    reads = []

    def handle(request):
        if request.method == "POST":
            assert request.url.path == "/v4/spreadsheets/as-file:batchUpdate"
            body = json.loads(request.content)
            posts.append(body)
            requests = body["requests"]
            assert len(requests) == (3 if expected_y else 2)
            assert [
                r["updateCells"]["range"]["startColumnIndex"] for r in requests
            ] == ([18, 23, 24] if expected_y else [18, 23])
            for r in requests:
                u = r["updateCells"]
                span = u["range"]
                assert (
                    span["sheetId"] == 7
                    and span["startRowIndex"] == 79
                    and span["endRowIndex"] == 80
                )
                assert span["endColumnIndex"] == span["startColumnIndex"] + 1
                assert len(u["rows"]) == 1 and len(u["rows"][0]["values"]) == 1
                assert "background" not in json.dumps(u)
            assert requests[0]["updateCells"]["rows"][0]["values"][0] == {
                "userEnteredValue": {"stringValue": "처리완료"}
            }
            assert requests[1]["updateCells"]["rows"][0]["values"][0] == {
                "userEnteredValue": {"numberValue": serial},
                "userEnteredFormat": {
                    "numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}
                },
            }
            assert (
                requests[1]["updateCells"]["fields"]
                == "userEnteredValue,userEnteredFormat.numberFormat"
            )
            if expected_y:
                assert requests[2]["updateCells"]["rows"][0]["values"][0][
                    "userEnteredValue"
                ] == {"stringValue": expected_y}
            if failure == "write_timeout":
                raise httpx.ReadTimeout("timeout", request=request)
            return httpx.Response(200, json={"replies": [{}] * len(requests)})
        assert request.method == "GET"
        if request.url.path.endswith("/values:batchGet"):
            reads.append(request.url.params.get_list("ranges"))
            values = [
                "다른이름" if failure == "changed_name" else "김 영호",
                "다른길1" if failure == "changed_address" else "영덕대게로 699",
                issue,
            ]
            if posts:
                assert request.url.params["valueRenderOption"] == "UNFORMATTED_VALUE"
                assert request.url.params["dateTimeRenderOption"] == "SERIAL_NUMBER"
                if failure == "readback_error":
                    return httpx.Response(503, json={})
                if failure == "changed_issue":
                    values[2] = "수정된 유형"
                values += [
                    "다름" if failure == "wrong_value" else "처리완료",
                    serial,
                ] + ([expected_y] if expected_y else [])
            return httpx.Response(
                200, json={"valueRanges": [{"values": [[v]]} for v in values]}
            )
        return httpx.Response(
            200,
            json={
                "sheets": [
                    {
                        "properties": {
                            "sheetId": 7,
                            "title": "AS' 관리",
                            "gridProperties": {
                                "rowCount": 79 if failure == "out_of_bounds" else 100,
                                "columnCount": 36,
                            },
                        }
                    }
                ]
            },
        )

    async def token():
        return "test"

    match = {
        "status": "found",
        "row": 80,
        "sheet_id": 7,
        "spreadsheet_id": "wrong" if failure == "wrong_target" else "as-file",
        "name": "김영호",
        "address": "영덕대게로699",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GoogleSheetsClient(
            "as-file",
            token,
            client=http,
            search_sheet_id=7,
            person_name_column="I",
            person_address_column="H",
            search_start_row=7,
        )
        result = await as_update.complete_as_row(client, match)
    if failure in ["changed_name", "changed_address", "out_of_bounds", "wrong_target"]:
        assert result["status"] == "failed" and not posts and not result["verified"]
    elif failure:
        assert (
            result["status"] == "unknown" and len(posts) == 1 and not result["verified"]
        )
    else:
        assert result["status"] == "updated" and result["verified"] and len(posts) == 1
        assert result["date"] == "2026-11-04"
        assert result["y_action"] == ("updated" if expected_y else "unchanged")
        assert reads[0] == ["'AS'' 관리'!I80", "'AS'' 관리'!H80", "'AS'' 관리'!C80"]
        assert reads[-1][3:] == ["'AS'' 관리'!S80", "'AS'' 관리'!X80"] + (
            ["'AS'' 관리'!Y80"] if expected_y else []
        )


def test_today_uses_korea_across_utc_midnight(monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026, 11, 3, 16, 0, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(as_update, "datetime", Clock)
    assert as_update.korea_today() == date(2026, 11, 4)
