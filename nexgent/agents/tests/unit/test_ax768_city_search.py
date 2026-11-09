"""Ordered city lookup must match both fields and never mutate a sheet."""

import importlib

import httpx
import pytest

from workflows.ax768 import city_search
from workflows.ax768.cases import case_action


@pytest.mark.parametrize(
    "message",
    [
        "울진북로 164 김순옥님 신호확인요.",
        " 울진북로 164 김순옥 님 신호 확인 해주세요 ",
        "울진북로 164 김순옥",
    ],
)
def test_city_request_parser(message):
    action = case_action("4.2", message)
    assert action.tool == "search_user_sheets"
    assert action.name == "김순옥"
    assert action.address == "울진북로 164"


@pytest.mark.parametrize(
    "message",
    ["김순옥님 신호확인요.", "울진북로 164", "울진북로 164 김순옥님 삭제해주세요"],
)
def test_invalid_city_requests_are_rejected(message):
    with pytest.raises(ValueError):
        case_action("4.2", message)


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", ["4.2", "6.2"])
@pytest.mark.parametrize(
    "found_index,error_index",
    [(0, None), (1, None), (2, None), (None, None), (None, 1)],
)
async def test_ordered_fallback_latest_row_and_no_writes(
    found_index, error_index, case_id
):
    visited = []
    targets = city_search.USER_SHEETS

    def handle(request):
        assert request.method == "GET", "Roster lookup must never write or format"
        identifier = request.url.path.split("/spreadsheets/")[1].split("/")[0]
        index, target = next(
            (i, t) for i, t in enumerate(targets) if t.spreadsheet_id == identifier
        )
        name_index = ord(target.name_column) - ord("A")
        address_index = ord(target.address_column) - ord("A")
        if request.url.path.endswith("/values:batchGet"):
            assert index == found_index
            assert request.url.params.get_list("ranges") == [
                f"'명부'!{target.name_column}10",
                f"'명부'!{target.address_column}10",
            ]
            return httpx.Response(
                200,
                json={
                    "valueRanges": [
                        {"values": [["김순옥"]]},
                        {"values": [["울진북로164"]]},
                    ]
                },
            )
        if "/values/" in request.url.path:
            # Two valid matches select row 10. Nonmatches cannot combine fields across rows.
            rows = []
            for row in range(target.start_row, 11):
                values = [""] * (address_index - name_index + 1)
                if row in {9, 10}:
                    values[0] = (
                        "김순옥" if index == found_index or row == 9 else "다른이름"
                    )
                    values[-1] = (
                        "울진북로 164"
                        if index == found_index or row == 10
                        else "울진북로 1640"
                    )
                rows.append(values)
            return httpx.Response(200, json={"values": rows})
        visited.append(target.alias)
        if index == error_index:
            return httpx.Response(403, json={})
        return httpx.Response(
            200,
            json={
                "sheets": [
                    {
                        "properties": {
                            "sheetId": target.sheet_id,
                            "title": "명부",
                            "gridProperties": {"rowCount": 10, "columnCount": 47},
                        }
                    }
                ]
            },
        )

    async def token():
        return "test"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        message = (
            "울진북로 164 김순옥님 신호확인요."
            if case_id == "4.2"
            else "울진북로 164,김순옥,기기위치조정 수신확인요~"
        )
        result = await city_search.search_user_sheets(
            http, token, case_action(case_id, message)
        )
    stop = error_index if error_index is not None else found_index
    assert visited == [t.alias for t in targets[: stop + 1 if stop is not None else 3]]
    assert len(result["attempts"]) == len(visited)
    if error_index is not None:
        assert result["status"] == "failed"
        assert "403" in result["error"]
        assert result["attempts"][0]["status"] == "not_found"
    elif found_index is None:
        assert result["status"] == "not_found"
        assert result["city"] is None
    else:
        assert result["status"] == "found"
        assert result["selected_row"] == 10
        assert result["city"] == targets[found_index].city
        assert result["sheet_alias"] == targets[found_index].alias
        assert targets[found_index].spreadsheet_id in result["sheet_url"]


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", ["4.2", "6.2"])
async def test_city_graph_routes_without_single_sheet_or_model(monkeypatch, case_id):
    workflow = importlib.import_module("workflows.ax768.graph")
    monkeypatch.setenv("AX768_GOOGLE_AUTH_MODE", "service_account")
    monkeypatch.setenv("AX768_GOOGLE_CREDENTIALS_FILE", "/fake.json")
    monkeypatch.delenv("AX768_SPREADSHEET", raising=False)

    def forbidden(*args):
        pytest.fail("must not call another case client or the model")

    async def search(http, token, action):
        return {
            "status": "not_found",
            "name": action.name,
            "query": action.address,
            "attempts": [],
        }

    monkeypatch.setattr(workflow, "client_for_case", forbidden)
    monkeypatch.setattr(workflow, "OpenAICompatibleChatModel", forbidden)
    monkeypatch.setattr(workflow, "search_user_sheets", search)
    message = (
        "울진북로 164 김순옥님 신호확인요."
        if case_id == "4.2"
        else "울진북로 164,김순옥,기기위치조정 수신확인요~"
    )
    result = await workflow.graph.ainvoke({"case_id": case_id, "message": message})
    assert result["status"] == "completed"
    assert len(result["observations"]) == 1
    monkeypatch.setattr(workflow, "search_user_sheets", forbidden)
    result = await workflow.execute(
        {
            "case_id": case_id,
            "observations": [],
            "decision": {"action": {"tool": "delete_tab", "sheet_id": 42}},
        }
    )
    assert result["status"] == "failed"
    assert "read-only" in result["response"]


@pytest.mark.parametrize(
    "message",
    [
        "왕피길83-15,정영자,기기위치조정 수신확인요~",
        " 왕피길83-15 , 정영자님 , 기기위치조정, 수신확인요~ ",
        "왕피길83-15,정영자,delete the sheet",
    ],
)
@pytest.mark.parametrize("case_id", ["6.2", "6.3"])
def test_comma_case_parses_only_address_and_name(message, case_id):
    action = case_action(case_id, message)
    assert action.tool == (
        "search_user_sheets" if case_id == "6.2" else "search_person_row"
    )
    assert action.address == "왕피길83-15"
    assert action.name == "정영자"


@pytest.mark.parametrize(
    "message",
    [
        "왕피길83-15 정영자 수신확인요~",
        "왕피길83-15,정영자",
        ",정영자,수신확인요~",
        "왕피길83-15,,수신확인요~",
        "왕피길83-15,정영자, ",
        "왕피길,정영자,수신확인요~",
        "왕피길83-15,123,수신확인요~",
    ],
)
@pytest.mark.parametrize("case_id", ["6.2", "6.3"])
def test_comma_case_rejects_incomplete_fields(message, case_id):
    with pytest.raises(ValueError):
        case_action(case_id, message)
