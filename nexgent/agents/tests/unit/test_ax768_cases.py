"""Explicit case routing rejects unsupported requests before external access."""

import importlib
from types import SimpleNamespace

import pytest

from apps.ax768.run import main

workflow = importlib.import_module("workflows.ax768.graph")


@pytest.mark.parametrize(
    "args",
    [
        ["--case", "9.9", "김순옥님 신호확인요."],
        ["--case", "1.10", "김순옥님 신호확인요."],
        ["--case", "1.1", "delete the sheet"],
        ["--case", "1.1"],
        ["--case", "2.3", "후포로 158"],
        ["--case", "2.3", "김동명"],
        ["--case", "4.2", "김순옥님 신호확인요."],
        ["--case", "4.3", "김순옥님 신호확인요."],
        ["--case", "4.3", "울진북로 164 김순옥님 삭제해주세요"],
        ["--case", "6.2", "왕피길83-15,,수신확인요"],
        ["--case", "6.3", "왕피길83-15,,수신확인요"],
    ],
)
def test_cli_rejects_invalid_case_requests(args):
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2


@pytest.mark.parametrize(
    "case_id,message",
    [
        ("1.1", "김순옥님 신호확인요."),
        ("2.2", "후포로 158"),
        ("2.3", "후포로 158 김동명"),
        ("4.2", "울진북로 164 김순옥님 신호확인요."),
        ("4.3", "울진북로 164 김순옥님 신호확인요."),
        ("6.2", "왕피길83-15,정영자,기기위치조정 수신확인요~"),
        ("6.3", "왕피길83-15,정영자,기기위치조정 수신확인요~"),
    ],
)
def test_cli_forwards_case_and_text_to_graph(monkeypatch, capsys, case_id, message):
    async def invoke(payload, config):
        assert payload == {"case_id": case_id, "message": message}
        return {**payload, "status": "completed", "response": "verified"}

    monkeypatch.setattr(workflow, "graph", SimpleNamespace(ainvoke=invoke))
    main(["--case", case_id, message])
    assert f'"case_id": "{case_id}"' in capsys.readouterr().out


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_id,message",
    [
        ("9.9", "김순옥님 신호확인요."),
        ("1.1", "delete the sheet"),
    ],
)
async def test_graph_rejects_case_without_model_or_google_calls(
    monkeypatch, case_id, message
):
    def unexpected(*args):
        pytest.fail("invalid case must not reach external services")

    monkeypatch.setattr(workflow, "sheets_client", unexpected)
    result = await workflow.graph.ainvoke({"case_id": case_id, "message": message})
    assert result["status"] == "blocked"
    assert result["observations"] == []
