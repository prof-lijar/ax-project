"""AX768 capability boundaries and realistic offline execution trajectories."""

import importlib
import json
from types import SimpleNamespace

import httpx
import pytest
from ax_contracts.sheets import SheetDecision
from ax_integrations.google_sheets import (
    GoogleSheetsClient,
    SheetsError,
    spreadsheet_id,
    validate_range,
)
from pydantic import ValidationError

workflow = importlib.import_module("workflows.ax768.graph")


def decision(tool, **kwargs):
    return SheetDecision.model_validate({"action": {"tool": tool, **kwargs}})


@pytest.mark.parametrize(
    "action",
    [
        {"tool": "shell", "command": "rm -rf /"},
        {"tool": "delete_rows", "sheet_id": 0, "start_index": 5, "end_index": 3},
        {"tool": "read_cells", "range": "Sales!A1", "spreadsheet_id": "other"},
        {"tool": "write_cells", "range": "Sales!A1", "values": [[{"formula": "evil"}]]},
        {"tool": "delete_tab", "sheet_id": "0"},
    ],
)
def test_rejects_untrusted_model_actions(action):
    with pytest.raises(ValidationError):
        SheetDecision.model_validate({"action": action})


@pytest.mark.parametrize("value", ["A1", "Sales!A:A", "Sales!A1:Z9999", "Sales!D4:A1"])
def test_rejects_unbounded_or_reversed_ranges(value):
    with pytest.raises(ValueError):
        validate_range(value)


def test_sheet_url_is_parsed_but_foreign_hosts_rejected():
    assert (
        spreadsheet_id("https://docs.google.com/spreadsheets/d/test-ID/edit#gid=0")
        == "test-ID"
    )
    with pytest.raises(ValueError):
        spreadsheet_id("https://evil.example/spreadsheets/d/other/edit")


@pytest.mark.asyncio
async def test_sheets_requests_keep_target_auth_and_delete_semantics():
    requests = []

    async def token():
        return "private-token"

    def handle(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer private-token"
        assert request.url.host == "sheets.googleapis.com"
        assert request.url.path.startswith("/v4/spreadsheets/fixed-ID")
        return httpx.Response(200, json={"updatedCells": 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GoogleSheetsClient("fixed-ID", token, client=http)
        await client.execute(
            decision("write_cells", range="Sales!B2", values=[[125]]).action
        )
        assert requests[-1].method == "PUT"
        assert requests[-1].url.params["valueInputOption"] == "RAW"
        await client.execute(
            decision("append_rows", range="Sales!A1:C5", values=[[1, 2, 3]]).action
        )
        assert requests[-1].method == "POST"
        assert requests[-1].url.path.endswith(":append")
        await client.execute(decision("clear_cells", range="Sales!B2").action)
        assert requests[-1].url.path.endswith(":clear")
        await client.execute(
            decision("delete_rows", sheet_id=17, start_index=1, end_index=3).action
        )
        assert json.loads(requests[-1].content) == {
            "requests": [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": 17,
                            "dimension": "ROWS",
                            "startIndex": 1,
                            "endIndex": 3,
                        },
                    }
                }
            ]
        }
        before = len(requests)
        with pytest.raises(ValueError, match="exceed"):
            await client.execute(
                decision("write_cells", range="Sales!A1", values=[[1, 2]]).action
            )
        assert len(requests) == before


@pytest.mark.asyncio
async def test_google_timeout_is_not_retried_or_leaked():
    calls = []

    async def token():
        return "secret"

    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret provider body", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GoogleSheetsClient("fixed-ID", token, client=http)
        with pytest.raises(SheetsError, match="outcome unknown") as error:
            await client.execute(
                decision("append_rows", range="Sales!A1", values=[[1]]).action
            )
    assert len(calls) == 1
    assert "secret" not in str(error.value)


def configure(monkeypatch, *, fail_write=False):
    monkeypatch.setenv("AX768_GOOGLE_AUTH_MODE", "service_account")
    monkeypatch.setenv("AX768_SPREADSHEET", "fixed-ID")
    monkeypatch.setenv("AX768_GOOGLE_CREDENTIALS_FILE", "/unused/private.json")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("OPENAI_MODEL", "local-test")
    monkeypatch.setenv("OPENAI_API_KEY", "local")
    actions = [
        decision("read_cells", range="Sales!B2"),
        decision("write_cells", range="Sales!B2", values=[[125]]),
        decision("read_cells", range="Sales!B2"),
        decision("finish", response="Updated B2 to 125 and verified it."),
    ]
    calls = []
    cell = [10]

    class Model:
        def __init__(self, settings):
            assert settings.model == "local-test"

        async def complete_structured(self, messages, **kwargs):
            return SimpleNamespace(text=actions.pop(0).model_dump_json())

        async def aclose(self):
            pass

    class Sheets:
        async def metadata(self):
            return {"sheets": [{"properties": {"sheetId": 17, "title": "Sales"}}]}

        async def execute(self, action):
            calls.append(action.tool)
            if action.tool == "write_cells":
                if fail_write:
                    raise SheetsError(
                        "Google request outcome unknown; inspect before replay"
                    )
                cell[0] = action.values[0][0]
                return {"updatedCells": 1}
            return {"values": [[cell[0]]]}

    monkeypatch.setattr(workflow, "OpenAICompatibleChatModel", Model)
    monkeypatch.setattr(workflow, "sheets_client", lambda http: Sheets())
    return calls


@pytest.mark.asyncio
async def test_read_update_verify_trajectory(monkeypatch):
    calls = configure(monkeypatch)
    result = await workflow.graph.ainvoke({"message": "Set Sales B2 to 125 and verify"})
    assert result["status"] == "completed"
    assert calls == ["read_cells", "write_cells", "read_cells"]
    assert result["observations"][-1]["result"]["values"] == [[125]]


@pytest.mark.asyncio
async def test_partial_failure_stops_before_finish_and_preserves_receipts(monkeypatch):
    calls = configure(monkeypatch, fail_write=True)
    result = await workflow.graph.ainvoke({"message": "Set Sales B2 to 125"})
    assert result["status"] == "failed"
    assert calls == ["read_cells", "write_cells"]
    assert result["observations"][1]["result"]["values"] == [[10]]
    assert "outcome unknown" in result["response"]


@pytest.mark.asyncio
async def test_missing_sheet_starts_fresh_without_any_external_call(monkeypatch):
    monkeypatch.delenv("AX768_SPREADSHEET", raising=False)
    result = await workflow.graph.ainvoke(
        {
            "message": "Read my sheet",
            "response": "stale success",
            "observations": [{"old": "sensitive"}],
            "steps": 10,
        }
    )
    assert result["status"] == "blocked"
    assert result["steps"] == 0
    assert result["observations"] == []
    assert "stale success" not in result["response"]


@pytest.mark.asyncio
async def test_step_limit_prevents_another_model_or_tool_call():
    result = await workflow.decide({"steps": workflow.MAX_STEPS})
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_structural_receipt_survives_verification_failure(monkeypatch):
    class Sheets:
        async def execute(self, action):
            return {"replies": [{"addSheet": {"properties": {"sheetId": 42}}}]}

        async def metadata(self):
            raise SheetsError("metadata unavailable")

    monkeypatch.setattr(workflow, "sheets_client", lambda http: Sheets())
    result = await workflow.execute(
        {
            "decision": decision("add_tab", title="New").model_dump(),
            "observations": [],
        }
    )
    assert result["status"] == "failed"
    assert (
        result["observations"][-1]["result"]["replies"][0]["addSheet"]["properties"][
            "sheetId"
        ]
        == 42
    )
