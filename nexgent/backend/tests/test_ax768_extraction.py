from dataclasses import replace
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ax768_extraction import ASSISTANT_ID, GRAPH
from conftest import authenticated_headers, feature_app

BODY = {'workflow_id': 'information_update', 'sources': [{'text': '연락처 010-0000-1234\n기타 참고 내용'}]}
FIELD = {'label': '연락처', 'value': '010-0000-1234', 'source_index': 0, 'uncertain': False}
PATH = '/api/ax768/workflow/extract'


def setup(monkeypatch, result=None, version='1', admin=True):
    requests = []
    async def upstream(request):
        requests.append(request)
        if request.method == 'GET':
            assert request.url.path == f'/assistants/{ASSISTANT_ID}/schemas'
            return httpx.Response(200, json={'input_schema': {'properties': {'extraction_version': {'const': version}}}})
        return httpx.Response(200, json=result if result is not None else {'status': 'completed', 'fields': [FIELD], 'sources': ['private raw excluded']})
    original = httpx.AsyncClient
    monkeypatch.setattr('app.ax768_extraction.httpx.AsyncClient', lambda **kw: original(transport=httpx.MockTransport(upstream), **kw))
    monkeypatch.setenv('AX_AGENT_SERVER_URL', 'http://agent:2024')
    app = feature_app()
    authenticate = app.state.identity_store.authenticate
    def account(token):
        value = authenticate(token)
        return replace(value, permissions=('access.manage',)) if value and admin else value
    app.state.identity_store.authenticate = account
    return TestClient(app), requests


def test_fixed_read_only_graph_and_minimal_result(monkeypatch):
    client, requests = setup(monkeypatch)
    response = client.post(PATH, headers=authenticated_headers(), json=BODY)
    assert response.status_code == 200
    assert response.json() == {'workflow_id': 'information_update', 'extraction_version': '1', 'fields': [FIELD]}
    sent = json.loads(requests[1].content)
    assert sent['assistant_id'] == GRAPH
    assert sent['input'] == {**BODY, 'extraction_version': '1'}
    assert sent['on_completion'] == 'delete' and sent['on_disconnect'] == 'cancel'
    assert len(requests) == 2 and 'cookie' not in requests[1].headers


def test_auth_and_csrf_before_any_call(monkeypatch):
    client, requests = setup(monkeypatch)
    assert client.post(PATH, json=BODY).status_code == 401
    assert client.post(PATH, json=BODY, headers={'Cookie': authenticated_headers()['Cookie']}).status_code == 403
    assert requests == []


def test_non_admin_is_denied(monkeypatch):
    client, requests = setup(monkeypatch, admin=False)
    assert client.post(PATH, json=BODY, headers=authenticated_headers()).status_code == 403
    assert requests == []


@pytest.mark.parametrize('change', [{'workflow_id': 'device_adjustment_power'}, {'sources': []}, {'sources': [{'text': ' '}]}, {'sources': [{'text': 'x'*8001}]}, {'sources': [{'text': 'x'}]*7}, {'images': []}])
def test_invalid_input(monkeypatch, change):
    client, requests = setup(monkeypatch)
    assert client.post(PATH, json={**BODY, **change}, headers=authenticated_headers()).status_code == 422
    assert requests == []


def test_stale_graph_blocked_before_run(monkeypatch):
    client, requests = setup(monkeypatch, version='0')
    assert client.post(PATH, json=BODY, headers=authenticated_headers()).status_code == 409
    assert len(requests) == 1


@pytest.mark.parametrize('result', [{'status': 'failed', 'fields': [FIELD]}, {'status': 'completed', 'fields': [{**FIELD, 'value': 'invented'}]}, {'status': 'completed', 'fields': [{**FIELD, 'source_index': 4}]}, {'status': 'completed', 'fields': [{**FIELD, 'source_index': True}]}, {'status': 'completed', 'fields': [FIELD]*201}])
def test_bad_results_never_become_valid_drafts(monkeypatch, result):
    client, _ = setup(monkeypatch, result=result)
    response = client.post(PATH, json=BODY, headers=authenticated_headers())
    assert response.status_code == 502 and 'fields' not in response.json()
