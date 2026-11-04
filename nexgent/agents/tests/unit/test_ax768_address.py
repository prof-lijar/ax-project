"""Address search returns rows from the correct file without any mutation."""

import importlib

import httpx
import pytest
from ax_contracts.sheets import FindAndHighlightAddressRow, SearchAddress
from ax_integrations import sheets_address
from ax_integrations.google_sheets import GoogleSheetsClient, SheetsError

from workflows.ax768.cases import case_action


@pytest.mark.parametrize(
    "value,expected",
    [
        ("경북 울진군 후포로 158", True),
        ("후포로158", True),
        ("후포로\n 158 (건물)", True),
        ("후포로 1580", False),
        ("후포로 1158", False),
        ("후포로 15", False),
    ],
)
def test_address_fragment_and_number_boundaries(value, expected):
    pattern = sheets_address.address_pattern("후포로 158")
    assert bool(pattern.search(sheets_address.normalize_address(value))) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("found", [True, False])
async def test_paged_search_returns_unique_rows_bottom_first_without_writes(
    monkeypatch, found
):
    monkeypatch.setattr(sheets_address, "PAGE_CELLS", 4)
    reads = []

    def handle(request):
        assert request.method == "GET"
        assert request.url.path.startswith("/v4/spreadsheets/address-file")
        if "/values/" not in request.url.path:
            return httpx.Response(
                200,
                json={
                    "sheets": [
                        {
                            "properties": {
                                "sheetId": 42,
                                "title": "주소",
                                "gridProperties": {"rowCount": 3, "columnCount": 2},
                            }
                        }
                    ]
                },
            )
        reads.append(request.url.path)
        values = (
            (
                [["후포로 158", "other"], ["후포로 1580"]]
                if len(reads) == 1
                else [["경북 후포로158", "후포로 158"]]
            )
            if found
            else []
        )
        return httpx.Response(200, json={"values": values})

    async def token():
        return "test"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GoogleSheetsClient(
            "address-file", token, client=http, search_sheet_id=42
        )
        result = await client.execute(
            SearchAddress(tool="search_address", address="후포로 158")
        )
    assert len(reads) == 2
    assert result["selected_row"] == (3 if found else None)
    assert result["match_count"] == (2 if found else 0)
    assert [m["row"] for m in result["matches"]] == ([3, 1] if found else [])


def test_case_2_2_validates_nonempty_address():
    assert case_action("2.2", " 후포로 158 ").address == "후포로 158"
    with pytest.raises(ValueError):
        case_action("2.2", "   ")


@pytest.mark.asyncio
@pytest.mark.parametrize("columns", ["G:H", "H:G", "X:Y", "G", "G:H1"])
async def test_address_column_scope_and_cell_offsets(columns):
    class Client:
        async def metadata(self):
            return {
                "sheets": [
                    {
                        "properties": {
                            "sheetId": 42,
                            "title": "주소",
                            "gridProperties": {"rowCount": 6000, "columnCount": 20},
                        }
                    }
                ]
            }

        async def _request(self, method, suffix, **kwargs):
            assert method == "GET"
            assert "G" in suffix and "H" in suffix
            if "G1%3A" in suffix:
                return {"values": [["", "후포로 158"]]}
            return {"values": []}

    if columns != "G:H":
        with pytest.raises(ValueError):
            await sheets_address.search_address(
                Client(), sheet_id=42, address="후포로 158", columns=columns
            )
        return
    result = await sheets_address.search_address(
        Client(), sheet_id=42, address="후포로 158", columns=columns
    )
    assert result["matches"] == [
        {
            "row": 1,
            "cells": [
                {
                    "cell": "'주소'!H1",
                    "address": "후포로 158",
                    "truncated": False,
                }
            ],
        }
    ]


@pytest.mark.asyncio
async def test_case_2_2_uses_own_client_and_no_model(monkeypatch):
    workflow = importlib.import_module("workflows.ax768.graph")
    monkeypatch.setenv("AX768_CASE_2_2_SPREADSHEET", "address-file")
    monkeypatch.setenv("AX768_CASE_2_2_SHEET_ID", "42")
    monkeypatch.setenv("AX768_GOOGLE_AUTH_MODE", "service_account")
    monkeypatch.setenv("AX768_GOOGLE_CREDENTIALS_FILE", "/fake.json")
    monkeypatch.delenv("AX768_SPREADSHEET", raising=False)

    class Client:
        async def metadata(self):
            return {}

        async def execute(self, action):
            assert action.tool == "find_and_highlight_address_row"
            return {"status": "not_found", "query": action.address}

    def forbidden(*args):
        pytest.fail("case 2.2 must not use general client/model")

    monkeypatch.setattr(workflow, "sheets_client", forbidden)
    monkeypatch.setattr(workflow, "OpenAICompatibleChatModel", forbidden)
    monkeypatch.setattr(workflow, "address_sheets_client", lambda http: Client())
    result = await workflow.graph.ainvoke({"case_id": "2.2", "message": "후포로 158"})
    assert result["status"] == "completed"
    assert "찾지 못했습니다" in result["response"]


@pytest.mark.asyncio
async def test_mutation_is_rejected_in_case_2_2_before_client_creation(monkeypatch):
    workflow = importlib.import_module("workflows.ax768.graph")

    def forbidden(*args):
        pytest.fail("must reject mutation before creating client")

    monkeypatch.setattr(workflow, "address_sheets_client", forbidden)
    result = await workflow.execute(
        {
            "case_id": "2.2",
            "observations": [],
            "decision": {
                "action": {"tool": "delete_tab", "sheet_id": 42},
            },
        }
    )
    assert result["status"] == "failed"
    assert "permits only" in result["response"]


@pytest.mark.asyncio
async def test_address_failure_does_not_return_incomplete_matches(monkeypatch):
    monkeypatch.setattr(sheets_address, "PAGE_CELLS", 4)

    class Client:
        async def metadata(self):
            return {
                "sheets": [
                    {
                        "properties": {
                            "sheetId": 42,
                            "title": "주소",
                            "gridProperties": {"rowCount": 3, "columnCount": 2},
                        }
                    }
                ]
            }

        async def _request(self, method, suffix, **kwargs):
            if "A1" in suffix:
                return {"values": [["후포로 158"]]}
            raise SheetsError("read failed")

    with pytest.raises(SheetsError, match="read failed"):
        await sheets_address.search_address(Client(), sheet_id=42, address="후포로 158")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "missing",
        "changed",
        "override",
        "write_error",
        "stored_missing",
        "missing_cell",
    ],
)
async def test_bottom_row_highlight_preserves_values_and_verifies_all_columns(scenario):
    writes = []
    color = {"backgroundColorStyle": {"rgbColor": {"red": 1, "green": 1}}}

    def handle(request):
        import json

        if request.method == "POST":
            writes.append(json.loads(request.content))
            if scenario == "write_error":
                return httpx.Response(403, json={"error": {"message": "forbidden"}})
            return httpx.Response(200, json={})
        if request.url.path.endswith("/values:batchGet"):
            assert request.url.params.get_list("ranges") == ["'주소'!H3"]
            return httpx.Response(
                200,
                json={
                    "valueRanges": [
                        {
                            "values": [
                                ["다른 주소" if scenario == "changed" else "후포로 158"]
                            ]
                        }
                    ]
                },
            )
        if "/values/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "values": []
                    if scenario == "missing"
                    else [["", "후포로 158"], [], ["", "후포로 158"]]
                },
            )
        if "ranges" in request.url.params:
            assert request.url.params.get_list("ranges") == ["'주소'!A3:J3"]
            cells = [
                {"userEnteredFormat": color, "effectiveFormat": color}
                for _ in range(10)
            ]
            if scenario == "override":
                cells[-1]["effectiveFormat"] = {}
            elif scenario == "stored_missing":
                cells[-1]["userEnteredFormat"] = {}
            elif scenario == "missing_cell":
                cells.pop()
            return httpx.Response(
                200,
                json={
                    "sheets": [
                        {"data": [{"startRow": 2, "rowData": [{"values": cells}]}]}
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "sheets": [
                    {
                        "properties": {
                            "sheetId": 42,
                            "title": "주소",
                            "gridProperties": {"rowCount": 3, "columnCount": 10},
                        }
                    }
                ]
            },
        )

    async def token():
        return "test"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GoogleSheetsClient(
            "address-file",
            token,
            client=http,
            search_sheet_id=42,
            address_columns="G:H",
        )
        action = FindAndHighlightAddressRow(
            tool="find_and_highlight_address_row", address="후포로 158"
        )
        if scenario in {"changed", "write_error"}:
            with pytest.raises(SheetsError):
                await client.execute(action)
            assert len(writes) == (1 if scenario == "write_error" else 0)
            return
        result = await client.execute(action)
    if scenario == "missing":
        assert result["status"] == "not_found"
        assert not writes
        return
    assert result["match_count"] == 2
    assert result["selected_row"] == 3
    assert result["verified"] is (scenario == "success")
    assert result["stored_verified"] is (scenario in {"success", "override"})
    assert result["overridden_cells"] == (
        ["'주소'!J3"] if scenario == "override" else []
    )
    assert result["status"] == (
        "highlighted"
        if scenario == "success"
        else "highlighted_with_warnings"
        if scenario == "override"
        else "verification_failed"
    )
    assert writes == [
        {
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": 42,
                            "startRowIndex": 2,
                            "endRowIndex": 3,
                            "startColumnIndex": 0,
                            "endColumnIndex": 10,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColorStyle": {
                                    "rgbColor": {"red": 1, "green": 1, "blue": 0}
                                }
                            }
                        },
                        "fields": "userEnteredFormat.backgroundColorStyle",
                    }
                }
            ]
        }
    ]


@pytest.mark.asyncio
async def test_unverified_row_highlight_is_not_completed(monkeypatch):
    workflow = importlib.import_module("workflows.ax768.graph")

    class Client:
        async def execute(self, action):
            return {
                "status": "verification_failed",
                "verified": False,
                "query": action.address,
                "match_count": 1,
                "selected_row": 3,
                "matches": [],
            }

    monkeypatch.setattr(workflow, "address_sheets_client", lambda http: Client())
    result = await workflow.execute(
        {
            "case_id": "2.2",
            "observations": [],
            "decision": {"action": case_action("2.2", "후포로 158").model_dump()},
        }
    )
    assert result["status"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", ["2.2", "2.3", "4.3", "6.3"])
async def test_saved_highlight_with_visible_override_completes_with_warning(
    monkeypatch, case_id
):
    workflow = importlib.import_module("workflows.ax768.graph")

    class Client:
        async def execute(self, action):
            result = {
                "status": "highlighted_with_warnings",
                "verified": False,
                "stored_verified": True,
                "query": action.address,
                "selected_row": 985,
                "match_count": 1,
                "matches": [],
                "highlighted_range": "'AS'!A985:AJ985",
                "overridden_cells": ["'AS'!C985"],
            }
            if case_id in {"2.3", "4.3", "6.3"}:
                result["name"] = action.name
            return result

    monkeypatch.setattr(workflow, "client_for_case", lambda http, case_id: Client())
    message = "오봉길 24 주정수" if case_id in {"2.3", "4.3"} else "오봉길 24"
    if case_id == "4.3":
        message += "님 신호확인요."
    elif case_id == "6.3":
        message = "오봉길 24,주정수,기기위치조정 수신확인요~"
    result = await workflow.execute(
        {
            "case_id": case_id,
            "observations": [],
            "decision": {"action": case_action(case_id, message).model_dump()},
        }
    )
    assert result["status"] == "completed"
    assert "배경 저장을 확인했습니다" in result["response"]
    assert "C985" in result["response"]
    assert "확인하지 못했습니다" not in result["response"]


@pytest.mark.asyncio
async def test_large_row_formatting_readback_requests_only_background_colors():
    """Unrelated formatting must not exhaust the unchanged response byte limit."""
    import json

    writes = []
    yellow = {"backgroundColorStyle": {"rgbColor": {"red": 1, "green": 1}}}
    full_format = {**yellow, "textFormat": {"fontFamily": "x" * 2000}}

    def payload(fmt):
        return {
            "sheets": [
                {
                    "data": [
                        {
                            "startRow": 3547,
                            "rowData": [
                                {
                                    "values": [
                                        {
                                            "userEnteredFormat": fmt,
                                            "effectiveFormat": fmt,
                                        }
                                        for _ in range(47)
                                    ]
                                }
                            ],
                        }
                    ]
                }
            ]
        }

    assert len(json.dumps(payload(full_format)).encode()) > 128000

    def handle(request):
        if request.method == "POST":
            writes.append(json.loads(request.content))
            return httpx.Response(200, json={})
        assert request.url.params.get_list("ranges") == ["'명부'!A3548:AU3548"]
        fields = request.url.params["fields"]
        narrow = all(
            f"{key}(backgroundColor,backgroundColorStyle)" in fields
            for key in ("userEnteredFormat", "effectiveFormat")
        )
        return httpx.Response(200, json=payload(yellow if narrow else full_format))

    async def token():
        return "test"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GoogleSheetsClient("fixed", token, client=http)
        result = await sheets_address.highlight_row_yellow(
            client, sheet_id=42, title="명부", row=3548, width=47
        )
    assert result["verified"] is True
    assert result["status"] == "highlighted"
    assert len(writes) == 1
