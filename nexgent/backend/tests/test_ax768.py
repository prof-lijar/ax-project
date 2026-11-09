from dataclasses import replace
from pathlib import Path
import ast
import json
from typing import get_args

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ax768 import AX768_ASSISTANT_ID, CaseId, normalize_result
from conftest import authenticated_headers, feature_app


def payload(status="found", *, state="completed", stored=True, visible=True):
    receipt = {"status": status, "name": "김순옥", "query": "울진북로 164", "selected_row": 44,
               "sheet_id": 42, "sheet_title": "명부", "city": "울진군", "sheet_alias": "uljin-users",
               "stored_verified": stored, "verified": visible, "match_count": 1,
               "overridden_cells": ["'명부'!C44"] if not visible else [],
               "overridden_cell_count": int(not visible), "attempts": [{"city": "울진군", "sheet_alias": "uljin-users", "status": "found"}]}
    return {"status": state, "response": "일치 행: 44", "observations": [
        {"tool": "metadata", "result": {"spreadsheetId": "fixed-id", "secret": "exclude-me"}},
        {"tool": "search_user_sheets", "arguments": {}, "result": receipt}
    ]}


def setup(monkeypatch, *, admin=True, result=None, status=200, error=None, search_only=True, imei_supported=True):
    requests = []
    async def upstream(request):
        if request.method == "GET":
            assert request.url.path == f"/assistants/{AX768_ASSISTANT_ID}/schemas"
            properties = {"case_policy": {"const": "search_only"}} if search_only else {}
            if imei_supported:
                properties["imei_case_version"] = {"const": "1"}
            return httpx.Response(200, json={"input_schema": {"properties": properties}})
        requests.append(request)
        if error:
            raise error("transport failed", request=request)
        return httpx.Response(status, json=payload() if result is None else result)
    original = httpx.AsyncClient
    monkeypatch.setattr("app.ax768.httpx.AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(upstream), **kwargs))
    monkeypatch.setenv("AX_AGENT_SERVER_URL", "http://private-agent:2024")
    app = feature_app()
    authenticate = app.state.identity_store.authenticate
    def account(token):
        value = authenticate(token)
        return replace(value, permissions=("access.manage",)) if value and admin else value
    app.state.identity_store.authenticate = account
    return TestClient(app), requests


def test_admin_csrf_allowlist_and_no_raw_graph_fields(monkeypatch):
    client, requests = setup(monkeypatch)
    body = {"case_id": "4.2", "message": "울진북로 164 김순옥님 신호확인요."}
    assert client.post("/api/ax768/runs", json=body).status_code == 401
    assert client.post("/api/ax768/runs", headers={"Cookie": authenticated_headers()["Cookie"]}, json=body).status_code == 403
    for invalid in ({**body, "case_id": "general"}, {**body, "assistant_id": "chat"}, {**body, "message": " "}, {**body, "message": "x" * 8001}):
        assert client.post("/api/ax768/runs", headers=authenticated_headers(), json=invalid).status_code == 422
    assert not requests
    response = client.post("/api/ax768/runs", headers=authenticated_headers(), json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["outcome"] == "found" and data["selected_row"] == 44
    assert data["sheet_url"] == "https://docs.google.com/spreadsheets/d/fixed-id/edit#gid=42&range=A44"
    assert "exclude-me" not in response.text and "observations" not in data
    sent = json.loads(requests[0].content)
    assert str(requests[0].url) == "http://private-agent:2024/runs/wait"
    assert sent == {"assistant_id": "ax768", "input": {**body, "case_policy": "search_only"}, "on_completion": "delete", "on_disconnect": "continue", "config": {"recursion_limit": 32}}
    assert "cookie" not in requests[0].headers and "x-csrf-token" not in requests[0].headers


def test_member_is_denied_before_execution(monkeypatch):
    client, requests = setup(monkeypatch, admin=False)
    assert client.post("/api/ax768/runs", headers=authenticated_headers(), json={"case_id": "4.2", "message": "text"}).status_code == 403
    assert requests == []


@pytest.mark.parametrize("operation,state,stored,visible,outcome", [
    ("found", "completed", True, True, "found"),
    ("not_found", "completed", True, True, "not_found"),
    ("highlighted", "completed", True, True, "highlighted"),
    ("highlighted_with_warnings", "completed", True, False, "highlighted_with_warnings"),
    ("highlighted", "completed", False, True, "failed"),
    ("verification_failed", "failed", False, False, "failed"),
])
def test_results_distinguish_saved_and_visible(operation, state, stored, visible, outcome):
    result = normalize_result(payload(operation, state=state, stored=stored, visible=visible), "2.2")
    assert result["outcome"] == outcome
    if operation == "highlighted_with_warnings":
        assert result["stored_verified"] is True and result["visible_verified"] is False
        assert result["overridden_cells"] == ["'명부'!C44"]


def test_blocked_without_receipt():
    assert normalize_result({"status": "blocked", "response": "Configure credentials", "observations": []}, "2.3")["outcome"] == "blocked"


@pytest.mark.parametrize("result", [{}, {"status": "completed", "response": "done"}, {"status": "running", "response": "wait"}, {"status": "completed", "response": 2}])
def test_malformed_result_is_uncertain(monkeypatch, result):
    client, requests = setup(monkeypatch, result=result)
    response = client.post("/api/ax768/runs", headers=authenticated_headers(), json={"case_id": "4.2", "message": "text"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ax768_outcome_unknown"
    assert len(requests) == 1


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
def test_no_automatic_retry_after_transport_failure(monkeypatch, error):
    client, requests = setup(monkeypatch, error=error)
    response = client.post("/api/ax768/runs", headers=authenticated_headers(), json={"case_id": "2.2", "message": "후포로 158"})
    assert response.status_code == 502 and len(requests) == 1


def test_case_allowlist_matches_workflow_registry():
    source = Path(__file__).resolve().parents[2] / "agents/workflows/ax768/cases.py"
    module = ast.parse(source.read_text())
    registry = next(ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CASE_DESCRIPTIONS" for t in node.targets))
    assert set(get_args(CaseId)) == set(registry)


def test_older_server_is_rejected_before_any_run(monkeypatch):
    client, requests = setup(monkeypatch, search_only=False)
    response = client.post("/api/ax768/runs", headers=authenticated_headers(), json={"case_id": "2.2", "message": "후포로 158"})
    assert response.status_code == 409
    assert requests == []


def imei_payload(connected=True):
    data=payload();result=data['observations'][-1]['result']
    result.update(status='connected' if connected else 'disconnected',imei='861212072106726',imei_column='Z',ping={
        'imei':'861212072106726','sn':'00300016','connected':connected,'fresh':connected,'elapsed_ms':1200,
        'signal_label':'보통','rssi':22,'cookie':'not-for-browser','raw':'not-for-browser'})
    return data


@pytest.mark.parametrize('connected',[True,False])
def test_imei_case_has_capability_guard_and_safe_result(monkeypatch,connected):
    client,requests=setup(monkeypatch,result=imei_payload(connected))
    response=client.post('/api/ax768/runs',json={'case_id':'imei','message':'김순옥님 신호확인요.'},headers=authenticated_headers())
    assert response.status_code==200
    data=response.json()
    assert data['outcome']==('connected' if connected else 'disconnected')
    assert data['ping']['sn']=='00300016' and data['imei_column']=='Z'
    assert data['response']==('S/N 00300016 신호 확인되었습니다.' if connected else 'S/N 00300016 전원 연결 및 기기위치 확인해주세요.')
    assert 'not-for-browser' not in response.text
    assert json.loads(requests[0].content)['input']['imei_case_version']=='1'


def test_old_runtime_does_not_receive_imei_case(monkeypatch):
    client,requests=setup(monkeypatch,imei_supported=False)
    assert client.post('/api/ax768/runs',json={'case_id':'imei','message':'김순옥님 신호확인요.'},headers=authenticated_headers()).status_code==409
    assert not requests


@pytest.mark.parametrize('change',[{'imei':'wrong'},{'sn':123},{'connected':'false'},{'fresh':False}])
def test_imei_receipt_requires_matching_identity_and_boolean_state(change):
    data=imei_payload();data['observations'][-1]['result']['ping'].update(change)
    with pytest.raises(ValueError):normalize_result(data,'imei')


def test_imei_roster_match_alone_is_not_signal_completion():
    with pytest.raises(ValueError):normalize_result(payload(),'imei')
