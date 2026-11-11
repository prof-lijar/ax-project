"""IMEI case must use the matching city column and report only verified signal states."""

import importlib
from types import SimpleNamespace

import httpx
import pytest
from ax_integrations.ansimk import AnsimkError

from apps.ax768.run import main
from workflows.ax768 import imei_case
from workflows.ax768.cases import case_action

IMEI = "861212072106726"


@pytest.mark.asyncio
@pytest.mark.parametrize("found_index", [0, 1, 2, None])
@pytest.mark.parametrize("connected", [True, False])
async def test_city_column_latest_row_and_korean_signal_message(
    monkeypatch, found_index, connected
):
    reads = []
    pings = []
    targets = imei_case.USER_SHEETS

    async def lookup(client, **kwargs):
        index = next(
            i for i, t in enumerate(targets) if client.base.endswith(t.spreadsheet_id)
        )
        reads.append(targets[index].alias)
        return {
            "status": "found" if index == found_index else "not_found",
            "row": 80,
            "name": "김순옥",
            "address": "울진북로164",
            "sheet_title": "명부'",
            "sheet_id": kwargs["sheet_id"],
        }

    monkeypatch.setattr(imei_case, "lookup_person", lookup)

    async def ping(value):
        pings.append(value)
        return {
            "imei": value,
            "sn": "00300016",
            "connected": connected,
            "fresh": connected,
            "elapsed_ms": 100,
            "rssi": 22,
            "signal_label": "보통",
        }

    monkeypatch.setattr(
        imei_case.AnsimkClient, "from_env", lambda _: SimpleNamespace(ping=ping)
    )

    def handle(request):
        assert request.method == "GET", "IMEI case must not mutate Sheets"
        target = targets[found_index]
        assert request.url.params.get_list("ranges") == [
            f"'명부'''!{target.name_column}80",
            f"'명부'''!{target.address_column}80",
            f"'명부'''!{imei_case.IMEI_COLUMNS[target.alias]}80",
        ]
        return httpx.Response(
            200,
            json={
                "valueRanges": [
                    {"values": [["김 순옥"]]},
                    {"values": [["울진북로 164"]]},
                    {"values": [[int(IMEI)]]},
                ]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        imei_case.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
    )

    async def token():
        return "test"

    output = await imei_case.run_imei_case('"김순옥님 신호확인요."', token)
    assert output["status"] == "completed"
    if found_index is None:
        assert len(reads) == 3 and not pings
        assert output["observations"][0]["result"]["status"] == "not_found"
    else:
        assert reads == [t.alias for t in targets[: found_index + 1]] and pings == [
            IMEI
        ]
        assert output["response"] == (
            "S/N 00300016 신호 확인되었습니다."
            if connected
            else "S/N 00300016 전원 연결 및 기기위치 확인해주세요."
        )
        receipt = output["observations"][0]["result"]
        assert receipt["imei_column"] == ["AA", "W", "Z"][found_index]
        assert (
            receipt["selected_row"] == 80
            and receipt["city"] == targets[found_index].city
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["no_imei", "invalid_imei", "changed_name", "read_error", "api_error"]
)
async def test_failed_lookup_or_ping_never_claims_disconnected(monkeypatch, failure):
    pings = []

    async def lookup(client, **kwargs):
        return {
            "status": "found",
            "row": 10,
            "name": "김순옥",
            "address": "울진북로164",
            "sheet_title": "명부",
        }

    monkeypatch.setattr(imei_case, "lookup_person", lookup)

    async def ping(value):
        pings.append(value)
        raise AnsimkError("API 연결 오류")

    monkeypatch.setattr(
        imei_case.AnsimkClient, "from_env", lambda _: SimpleNamespace(ping=ping)
    )

    def handle(request):
        if failure == "read_error":
            return httpx.Response(403, json={})
        return httpx.Response(
            200,
            json={
                "valueRanges": [
                    {
                        "values": [
                            ["다른이름" if failure == "changed_name" else "김순옥"]
                        ]
                    },
                    {"values": [["울진북로164"]]},
                    {
                        "values": [
                            [
                                ""
                                if failure == "no_imei"
                                else "123"
                                if failure == "invalid_imei"
                                else IMEI
                            ]
                        ]
                    },
                ]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        imei_case.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
    )

    async def token():
        return "test"

    output = await imei_case.run_imei_case("김순옥님 신호확인요.", token)
    assert output["status"] == "failed"
    assert "전원 연결 및 기기위치 확인해주세요" not in output["response"]
    assert len(pings) == (1 if failure == "api_error" else 0)


def test_imei_parser_and_cli(monkeypatch, capsys):
    assert case_action("imei", "김순옥님 신호확인요.") is None
    with pytest.raises(ValueError):
        case_action("imei", "delete all")
    graph = importlib.import_module("workflows.ax768.graph")

    async def invoke(payload, config):
        assert payload == {"case_id": "imei", "message": "김순옥님 신호확인요."}
        return {**payload, "status": "completed", "response": "ok"}

    monkeypatch.setattr(graph, "graph", SimpleNamespace(ainvoke=invoke))
    main(["--case", "imei", "김순옥님 신호확인요."])
    assert '"case_id": "imei"' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_graph_routes_imei_without_as_or_model(monkeypatch):
    graph = importlib.import_module("workflows.ax768.graph")
    monkeypatch.setenv("AX768_GOOGLE_AUTH_MODE", "service_account")
    monkeypatch.setenv("AX768_GOOGLE_CREDENTIALS_FILE", "unused")
    monkeypatch.delenv("AX768_SPREADSHEET", raising=False)

    async def run(message, token):
        return {"status": "completed", "response": "signal result", "observations": []}

    monkeypatch.setattr(imei_case, "run_imei_case", run)

    def forbidden(*a, **kw):
        pytest.fail("No model or AS client is permitted")

    monkeypatch.setattr(graph, "person_sheets_client", forbidden)
    monkeypatch.setattr(graph, "OpenAICompatibleChatModel", forbidden)
    output = await graph.graph.ainvoke(
        {"case_id": "imei", "message": "김순옥님 신호확인요."}
    )
    assert output["status"] == "completed" and output["response"] == "signal result"
    assert (
        graph.graph.get_input_jsonschema()["properties"]["imei_case_version"]["const"]
        == "1"
    )
