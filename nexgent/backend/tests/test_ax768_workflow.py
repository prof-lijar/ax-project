from dataclasses import replace
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from app.ax768_workflow import ASSISTANT_ID, normalize
from conftest import authenticated_headers, feature_app


def payload():
    match = {'status': 'found', 'row': 44, 'name': '김순옥', 'address': '울진북로164', 'spreadsheet_id': 'sheet-id', 'sheet_id': 7, 'sheet_alias': 'uljin-users', 'city': '울진군', 'secret': 'exclude-me', 'sheet_url': 'https://evil.invalid/'}
    return {'status': 'completed', 'response': 'AS 80행', 'parsed': {'name': '김순옥', 'lookup_name': '김순옥', 'address': '울진북로 164'}, 'roster': match, 'as_lookup': {**match, 'row': 80, 'sheet_alias': 'AS'}, 'attempts': [], 'candidates': [], 'notices': [], 'as_update': {'status':'updated','row':80,'date':'2026-11-04','changes':[{'column':'S','value':'처리완료'},{'column':'X','value':'2026-11-04'}],'y_action':'unchanged','verified':True,'reason':'saved'}}


def setup(monkeypatch, *, admin=True, result=None, schema_status=200, version='3', error=False):
    requests=[]
    async def upstream(request):
        if request.method == 'GET':
            assert request.url.path == f'/assistants/{ASSISTANT_ID}/schemas'
            return httpx.Response(schema_status, json={'input_schema': {'properties': {'workflow_version': {'const': version}}}})
        requests.append(request)
        if error: raise httpx.ReadTimeout('timeout', request=request)
        return httpx.Response(200, json=payload() if result is None else result)
    original=httpx.AsyncClient
    monkeypatch.setattr('app.ax768_workflow.httpx.AsyncClient', lambda **kw: original(transport=httpx.MockTransport(upstream), **kw))
    monkeypatch.setenv('AX_AGENT_SERVER_URL', 'http://agent:2024')
    app=feature_app(); authenticate=app.state.identity_store.authenticate
    def account(token):
        value=authenticate(token)
        return replace(value, permissions=('access.manage',)) if value and admin else value
    app.state.identity_store.authenticate=account
    return TestClient(app), requests


BODY={'message': '울진북로 164 김순옥님 신호확인요.'}
PATH='/api/ax768/workflow/runs'


def test_permissions_validation_and_fixed_graph(monkeypatch):
    client, requests=setup(monkeypatch)
    assert client.post(PATH, json=BODY).status_code == 401
    assert client.post(PATH, json=BODY, headers={'Cookie': authenticated_headers()['Cookie']}).status_code == 403
    for invalid in ({**BODY, 'region':'seoul'}, {**BODY, 'message':' '}, {**BODY,'message':'x'*8001}, {**BODY,'spreadsheet':'other'}, {**BODY, 'images':[]}):
        assert client.post(PATH, json=invalid, headers=authenticated_headers()).status_code == 422
    assert not requests
    response=client.post(PATH, json=BODY, headers=authenticated_headers())
    assert response.status_code == 200
    data=response.json()
    assert data['roster']['row'] == 44 and data['as_lookup']['row'] == 80
    assert data['roster']['sheet_url'] == 'https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=7&range=A44'
    assert 'evil.invalid' not in response.text and 'exclude-me' not in response.text
    sent=json.loads(requests[0].content)
    assert sent == {'assistant_id':'ax768_workflow','input':{**BODY,'confirmed_name':None,'workflow_version':'3'},'on_completion':'delete','on_disconnect':'continue','config':{'recursion_limit':32}}
    assert 'cookie' not in requests[0].headers


def test_members_cannot_run(monkeypatch):
    client, requests=setup(monkeypatch, admin=False)
    assert client.post(PATH,json=BODY,headers=authenticated_headers()).status_code == 403
    assert not requests


@pytest.mark.parametrize('schema_status,version', [(404,'3'),(200,'2'),(200,'1'),(200,'old')])
def test_missing_or_stale_graph_is_blocked_before_run(monkeypatch,schema_status,version):
    client,requests=setup(monkeypatch,schema_status=schema_status,version=version)
    assert client.post(PATH,json=BODY,headers=authenticated_headers()).status_code == 409
    assert not requests


@pytest.mark.parametrize('bad', [{}, {'status':'completed','response':'done'}, {**payload(), 'as_lookup':{'status':'not_found'}}, {**payload(),'roster':{'status':'found','row':3}}, {**payload(),'notices':None}])
def test_bad_evidence_returns_unknown(monkeypatch,bad):
    client,requests=setup(monkeypatch,result=bad)
    assert client.post(PATH,json=BODY,headers=authenticated_headers()).status_code == 502
    assert len(requests) == 1


def test_timeout_does_not_retry(monkeypatch):
    client,requests=setup(monkeypatch,error=True)
    assert client.post(PATH,json=BODY,headers=authenticated_headers()).status_code == 502
    assert len(requests) == 1


def test_partial_as_failure_keeps_roster():
    result=normalize({**payload(),'status':'failed','as_lookup':{'status':'failed'},'as_update':{'status':'skipped','verified':False}})
    assert result['roster']['row'] == 44 and result['as_lookup']['status'] == 'failed'


def test_confirmation_forwarded_and_bounded(monkeypatch):
    client, requests=setup(monkeypatch)
    assert client.post(PATH,json={**BODY,'confirmed_name':'김영호'},headers=authenticated_headers()).status_code == 200
    assert json.loads(requests[0].content)['input']['confirmed_name'] == '김영호'


@pytest.mark.parametrize('change', [
    {'verified':False}, {'row':999}, {'changes':[]}, {'status':'unknown','verified':False},
    {'changes':[{'column':'S','value':'처리완료'},{'column':'X','value':'2026-11-05'}]},
    {'date':'2026-99-99'}, {'y_action':'updated'},
    {'changes':[{'column':'A','value':'not allowed'}]},
])
def test_completion_requires_exact_verified_update(monkeypatch,change):
    result=payload(); result['as_update'].update(change)
    client,_=setup(monkeypatch,result=result)
    assert client.post(PATH,json=BODY,headers=authenticated_headers()).status_code == 502


def test_unknown_update_keeps_matches_without_claiming_saved():
    result=payload(); result['status']='failed'; result['as_update'].update(status='unknown',verified=False)
    normalized=normalize(result)
    assert normalized['as_lookup']['row']==80 and normalized['roster']['row']==44
    assert normalized['as_update']['status']=='unknown' and not normalized['as_update']['verified']


def test_both_y_rules_are_allowed():
    for value in ['위치점검완료','전원연결완료']:
        result=payload(); result['as_update']['changes'].append({'column':'Y','value':value})
        result['as_update']['y_action']='updated'
        assert normalize(result)['as_update']['changes'][-1]['value']==value
