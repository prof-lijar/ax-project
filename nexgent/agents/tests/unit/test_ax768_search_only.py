"""Numbered cases find latest rows using only Google GET requests."""

import importlib
import re
from urllib.parse import unquote

import httpx
import pytest
from ax_integrations.google_sheets import GoogleSheetsClient

workflow = importlib.import_module("workflows.ax768.graph")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_id,message",
    [
        ("1.1", "김순옥님 신호확인요."),
        (None, "김순옥님 신호확인요."),
        ("2.2", "울진북로 164"),
        ("2.3", "울진북로 164 김순옥"),
        ("4.3", "울진북로 164 김순옥님 신호확인요."),
        ("6.3", "울진북로 164,김순옥,신호확인요"),
    ],
)
async def test_latest_match_is_returned_without_any_write(
    monkeypatch, case_id, message
):
    calls = []
    rows = [[""] * 7 + ["울진북로 164", "김순옥"] for _ in range(3)]

    async def upstream(request):
        calls.append(request)
        assert request.method == "GET", "search must never send a Google write"
        path = unquote(request.url.path)
        if path.endswith("/values:batchGet"):
            return httpx.Response(
                200,
                json={
                    "valueRanges": [
                        {"values": [["김순옥" if "!I" in span else "울진북로 164"]]}
                        for span in request.url.params.get_list("ranges")
                    ]
                },
            )
        if "/values/" in path:
            match = re.search(r"!([A-I])(\d+):([A-I])(\d+)$", path)
            assert match, path
            left, top, right, bottom = match.groups()
            return httpx.Response(
                200,
                json={
                    "values": [
                        row[ord(left) - 65 : ord(right) - 64]
                        for row in rows[int(top) - 1 : int(bottom)]
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "spreadsheetId": "fixed",
                "sheets": [
                    {
                        "properties": {
                            "sheetId": 42,
                            "title": "AS",
                            "gridProperties": {"rowCount": 3, "columnCount": 9},
                        }
                    }
                ],
            },
        )

    async def token():
        return "fixture-token"

    for key in (
        "AX768_SPREADSHEET",
        "AX768_CASE_2_2_SPREADSHEET",
        "AX768_CASE_2_2_SHEET_ID",
        "AX768_CASE_2_3_SPREADSHEET",
        "AX768_CASE_2_3_SHEET_ID",
        "AX768_CASE_2_3_NAME_COLUMN",
        "AX768_CASE_2_3_ADDRESS_COLUMN",
        "AX768_CASE_2_3_START_ROW",
        "AX768_GOOGLE_CREDENTIALS_FILE",
    ):
        monkeypatch.setenv(key, "fixture")
    monkeypatch.setenv("AX768_GOOGLE_AUTH_MODE", "service_account")
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as http:
        sheets = GoogleSheetsClient(
            "fixed",
            token,
            client=http,
            search_sheet_id=42,
            address_columns="H:H",
            person_name_column="I",
            person_address_column="H",
        )
        monkeypatch.setattr(workflow, "client_for_case", lambda *_: sheets)
        result = await workflow.graph.ainvoke({"case_id": case_id, "message": message})
    assert result["status"] == "completed"
    receipt = result["observations"][-1]
    assert receipt["tool"].startswith("search_")
    assert receipt["result"]["status"] == "found"
    assert receipt["result"]["selected_row"] == 3
    assert "노란색" not in result["response"]
    assert calls and all(request.method == "GET" for request in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    [
        {"tool": "find_and_highlight_name", "name": "김순옥"},
        {"tool": "find_and_highlight_address_row", "address": "울진북로 164"},
        {
            "tool": "find_and_highlight_person_row",
            "name": "김순옥",
            "address": "울진북로 164",
        },
    ],
)
async def test_legacy_highlight_decisions_cannot_execute(monkeypatch, action):
    def forbidden(*args):
        pytest.fail("Legacy highlighting must be rejected before creating a client")

    monkeypatch.setattr(workflow, "client_for_case", forbidden)
    result = await workflow.execute(
        {"observations": [], "decision": {"action": action}}
    )
    assert result["status"] == "failed"
    assert "highlighting is disabled" in result["response"]
