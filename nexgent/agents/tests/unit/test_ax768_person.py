"""AS name/address must match the same bottom-most row before formatting."""

import importlib
import json

import httpx
import pytest
from ax_integrations import sheets_person
from ax_integrations.google_sheets import GoogleSheetsClient, SheetsError

from workflows.ax768.cases import case_action


def test_case_2_3_parses_address_then_name():
    action = case_action("2.3", " 후포로 158 김동명 ")
    assert action.name == "김동명"
    assert action.address == "후포로 158"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "latest",
        "older",
        "missing",
        "name_changed",
        "address_changed",
        "read_error",
        "override",
    ],
)
async def test_bottom_up_match_and_verified_highlight(monkeypatch, scenario):
    monkeypatch.setattr(sheets_person, "PAGE_CELLS", 4)
    reads, writes = [], []
    selected = 8 if scenario == "older" else 10
    color = {"backgroundColorStyle": {"rgbColor": {"red": 1, "green": 1}}}

    def handle(request):
        assert request.url.path.startswith("/v4/spreadsheets/as-file")
        if request.method == "POST":
            writes.append(json.loads(request.content))
            return httpx.Response(200, json={})
        if request.url.path.endswith("/values:batchGet"):
            assert request.url.params.get_list("ranges") == [
                f"'AS'!I{selected}",
                f"'AS'!H{selected}",
            ]
            return httpx.Response(
                200,
                json={
                    "valueRanges": [
                        {
                            "values": [
                                ["다른이름" if scenario == "name_changed" else "김동명"]
                            ]
                        },
                        {
                            "values": [
                                [
                                    "후포로 1580"
                                    if scenario == "address_changed"
                                    else "후포로158"
                                ]
                            ]
                        },
                    ]
                },
            )
        if "/values/" in request.url.path:
            span = request.url.path.split("/values/")[1]
            reads.append(span)
            if scenario == "read_error":
                return httpx.Response(503, json={})
            # Cross-row and near-number candidates must never match.
            unmatched = [["후포로 158", "김다름"], ["후포로 1580", "김동명"]]
            values = (
                unmatched
                if scenario == "missing" or (scenario == "older" and len(reads) == 1)
                else [["후포로 158", "김동명"], ["경북 후포로158", " 김동명 "]]
            )
            return httpx.Response(200, json={"values": values})
        if "ranges" in request.url.params:
            assert request.url.params.get_list("ranges") == [
                f"'AS'!A{selected}:J{selected}"
            ]
            cells = [
                {"userEnteredFormat": color, "effectiveFormat": color}
                for _ in range(10)
            ]
            if scenario == "override":
                cells[-1]["effectiveFormat"] = {}
            return httpx.Response(
                200,
                json={
                    "sheets": [
                        {
                            "data": [
                                {
                                    "startRow": selected - 1,
                                    "rowData": [{"values": cells}],
                                }
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
                            "sheetId": 42,
                            "title": "AS",
                            "gridProperties": {"rowCount": 10, "columnCount": 10},
                        }
                    }
                ]
            },
        )

    async def token():
        return "test"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GoogleSheetsClient(
            "as-file",
            token,
            client=http,
            search_sheet_id=42,
            person_name_column="I",
            person_address_column="H",
            search_start_row=7,
        )
        action = case_action("2.3", "후포로 158 김동명")
        if scenario in {"name_changed", "address_changed", "read_error"}:
            with pytest.raises(SheetsError):
                await client.execute(action)
            assert not writes
            return
        result = await client.execute(action)
    assert reads[0] == "'AS'!H9:I10"
    if scenario in {"older", "missing"}:
        assert reads == ["'AS'!H9:I10", "'AS'!H7:I8"]
    else:
        assert len(reads) == 1
    if scenario == "missing":
        assert result["status"] == "not_found"
        assert not writes
        return
    assert result["selected_row"] == selected
    assert result["verified"] is (scenario != "override")
    assert result["stored_verified"] is True
    assert result["status"] == (
        "highlighted_with_warnings" if scenario == "override" else "highlighted"
    )
    assert len(writes) == 1
    operation = writes[0]["requests"][0]["repeatCell"]
    assert operation["range"] == {
        "sheetId": 42,
        "startRowIndex": selected - 1,
        "endRowIndex": selected,
        "startColumnIndex": 0,
        "endColumnIndex": 10,
    }
    assert operation["fields"] == "userEnteredFormat.backgroundColorStyle"
    assert set(operation["cell"]) == {"userEnteredFormat"}


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", ["2.3", "4.3", "6.3"])
async def test_as_graph_isolated_and_rejects_other_tools(monkeypatch, case_id):
    workflow = importlib.import_module("workflows.ax768.graph")
    for key, value in {
        "SPREADSHEET": "as-file",
        "SHEET_ID": "42",
        "NAME_COLUMN": "I",
        "ADDRESS_COLUMN": "H",
        "START_ROW": "7",
    }.items():
        monkeypatch.setenv("AX768_CASE_2_3_" + key, value)
    monkeypatch.setenv("AX768_GOOGLE_AUTH_MODE", "service_account")
    monkeypatch.setenv("AX768_GOOGLE_CREDENTIALS_FILE", "/fake.json")
    monkeypatch.delenv("AX768_SPREADSHEET", raising=False)

    def forbidden(*args):
        pytest.fail("must not use another case client or model")

    class Client:
        async def metadata(self):
            return {}

        async def execute(self, action):
            assert action.name == "김동명"
            return {
                "name": action.name,
                "query": action.address,
                "status": "not_found",
                "verified": True,
            }

    monkeypatch.setattr(workflow, "person_sheets_client", lambda http: Client())
    monkeypatch.setattr(workflow, "sheets_client", forbidden)
    monkeypatch.setattr(workflow, "address_sheets_client", forbidden)
    monkeypatch.setattr(workflow, "OpenAICompatibleChatModel", forbidden)
    monkeypatch.setattr(workflow, "search_user_sheets", forbidden)
    message = "후포로 158 김동명" + ("님 신호확인요." if case_id == "4.3" else "")
    if case_id == "6.3":
        message = "후포로 158,김동명,기기위치조정 수신확인요~"
    result = await workflow.graph.ainvoke({"case_id": case_id, "message": message})
    assert result["status"] == "completed"
    monkeypatch.setattr(workflow, "person_sheets_client", forbidden)
    result = await workflow.execute(
        {
            "case_id": case_id,
            "observations": [],
            "decision": {"action": {"tool": "delete_tab", "sheet_id": 42}},
        }
    )
    assert result["status"] == "failed"
