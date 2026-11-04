"""Exact-name search, formatting scope, pagination and verification gates."""

import importlib
import json

import httpx
import pytest
from ax_contracts.sheets import FindAndHighlightName
from ax_integrations import sheets_highlight
from ax_integrations.google_sheets import GoogleSheetsClient, SheetsError

from workflows.ax768.signal_check import requested_name


@pytest.mark.parametrize(
    "text", ["김순옥님 신호확인요.", " 김순옥님 신호 확인 해주세요 "]
)
def test_korean_shorthand(text):
    assert requested_name(text) == "김순옥"
    assert requested_name("김순옥님 삭제해 주세요") is None


def fixture_transport(*, found=True, changed=False, overridden=False, rows=3):
    writes = []
    reads = []
    yellow = {"backgroundColorStyle": {"rgbColor": {"red": 1, "green": 1}}}

    def handle(request):
        assert request.url.path.startswith("/v4/spreadsheets/fixed")
        if request.method == "POST":
            writes.append(json.loads(request.content))
            return httpx.Response(200, json={"replies": [{}, {}]})
        if request.url.path.endswith("/values:batchGet"):
            assert request.url.params.get_list("ranges") == ["'명단'!B3"]
            values = [
                {"values": [] if changed else [["김순옥"]]},
            ]
            return httpx.Response(200, json={"valueRanges": values})
        if "/values/" in request.url.path:
            reads.append(request.url.path)
            assert "'명단'!" in request.url.path
            values = (
                (
                    [["김순옥", "김순옥님"], ["김순옥 (보호자)"]]
                    if len(reads) == 1
                    else [["", " 김순옥 "]]
                )
                if found
                else []
            )
            return httpx.Response(200, json={"values": values})
        if "ranges" in request.url.params:
            fields = request.url.params["fields"]
            assert "userEnteredFormat(backgroundColor,backgroundColorStyle)" in fields
            assert "effectiveFormat(backgroundColor,backgroundColorStyle)" in fields
            assert "formattedValue" in fields
            cell = {
                "formattedValue": "김순옥",
                "userEnteredFormat": yellow,
                "effectiveFormat": {} if overridden else yellow,
            }
            return httpx.Response(
                200,
                json={
                    "sheets": [
                        {
                            "data": [
                                {
                                    "startRow": 0,
                                    "startColumn": 0,
                                    "rowData": [{"values": [cell]}],
                                },
                                {
                                    "startRow": 2,
                                    "startColumn": 1,
                                    "rowData": [{"values": [cell]}],
                                },
                            ]
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "sheets": [
                    {
                        "properties": {
                            "sheetId": 99,
                            "title": "other",
                            "gridProperties": {"rowCount": 1, "columnCount": 1},
                        }
                    },
                    {
                        "properties": {
                            "sheetId": 42,
                            "title": "명단",
                            "gridProperties": {"rowCount": rows, "columnCount": 3},
                        }
                    },
                ]
            },
        )

    return httpx.MockTransport(handle), writes, reads


async def run_search(monkeypatch, **kwargs):
    monkeypatch.setattr(sheets_highlight, "PAGE_CELLS", 6)
    transport, writes, reads = fixture_transport(**kwargs)

    async def token():
        return "test"

    async with httpx.AsyncClient(transport=transport) as http:
        client = GoogleSheetsClient("fixed", token, client=http, search_sheet_id=42)
        result = await client.execute(
            FindAndHighlightName(tool="find_and_highlight_name", name="김순옥")
        )
    return result, writes, reads


@pytest.mark.asyncio
async def test_matches_across_pages_only_highlight_bottommost_name(monkeypatch):
    result, writes, reads = await run_search(monkeypatch)
    assert len(reads) == 2
    assert result["verified"]
    assert result["matched_cells"] == ["'명단'!B3"]
    assert result["total_match_count"] == 2
    assert result["selected_row"] == 3
    assert result["match_count"] == 1
    assert len(writes) == 1
    assert len(writes[0]["requests"]) == 1
    for request in writes[0]["requests"]:
        update = request["repeatCell"]
        assert update["fields"] == "userEnteredFormat.backgroundColorStyle"
        assert set(update["cell"]) == {"userEnteredFormat"}
        assert update["range"]["sheetId"] == 42
        assert update["range"]["startRowIndex"] == 2
        assert update["range"]["startColumnIndex"] == 1
        assert update["range"]["endRowIndex"] - update["range"]["startRowIndex"] == 1
        assert (
            update["range"]["endColumnIndex"] - update["range"]["startColumnIndex"] == 1
        )


@pytest.mark.asyncio
async def test_not_found_never_writes(monkeypatch):
    result, writes, _ = await run_search(monkeypatch, found=False)
    assert result["status"] == "not_found"
    assert writes == []


@pytest.mark.asyncio
async def test_conditional_format_override_is_not_claimed_verified(monkeypatch):
    result, writes, _ = await run_search(monkeypatch, overridden=True)
    assert result["status"] == "verification_failed"
    assert not result["verified"]
    assert len(writes) == 1


@pytest.mark.asyncio
async def test_changed_name_stops_before_write(monkeypatch):
    with pytest.raises(SheetsError, match="changed"):
        await run_search(monkeypatch, changed=True)


@pytest.mark.asyncio
async def test_oversized_grid_fails_before_partial_search(monkeypatch):
    with pytest.raises(SheetsError, match="100,000"):
        await run_search(monkeypatch, rows=100001)


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", [None, "1.1"])
async def test_graph_shorthand_only_dispatches_name_highlight(monkeypatch, case_id):
    workflow = importlib.import_module("workflows.ax768.graph")
    monkeypatch.setenv("AX768_GOOGLE_AUTH_MODE", "service_account")
    monkeypatch.setenv("AX768_GOOGLE_CREDENTIALS_FILE", "/fake.json")
    monkeypatch.setenv("AX768_SPREADSHEET", "fixed")
    calls = []

    class Sheets:
        async def metadata(self):
            return {}

        async def execute(self, action):
            calls.append(action)
            return {
                "name": action.name,
                "verified": True,
                "status": "highlighted",
                "match_count": 1,
                "matched_cells": ["'명단'!B81"],
            }

    def no_model(*args):
        pytest.fail("shorthand must not call unrestricted model actions")

    monkeypatch.setattr(workflow, "sheets_client", lambda http: Sheets())
    monkeypatch.setattr(workflow, "OpenAICompatibleChatModel", no_model)
    result = await workflow.graph.ainvoke(
        {"message": "김순옥님 신호확인요.", "case_id": case_id}
    )
    assert result["status"] == "completed"
    assert len(calls) == 1 and calls[0].name == "김순옥"
    assert "노란색" in result["response"]
