import copy
import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ax768 import normalize_result
from conftest import authenticated_headers, feature_app

NOTE = '2026-10-28 [현지관리자 방문] 기기위치조정'
BODY = {'case_id': 'member_note', 'message': f'이름: 이은경\n일반 사항: {NOTE}'}


def receipt(status='saved'):
    return {'status':'completed' if status in {'saved','already_present','not_found'} else 'blocked' if status=='needs_confirmation' else 'failed', 'response':'확인', 'observations':[{'tool':'member_general_note','result':{
        'status':status,'member_id':12,'name':'이은경','address':'테스트로 1','note':NOTE,
        'verified':status in {'saved','already_present'},'candidates':[], 'secret':'excluded'}}]}


def client(monkeypatch, version='2', result=None):
    requests=[]
    async def upstream(request):
        if request.method=='GET':
            return httpx.Response(200,json={'input_schema':{'properties':{'member_note_case_version':{'const':version}}}})
        requests.append(request)
        return httpx.Response(200,json=result or receipt())
    original=httpx.AsyncClient
    monkeypatch.setattr('app.ax768.httpx.AsyncClient',lambda **kw:original(transport=httpx.MockTransport(upstream),**kw))
    app=feature_app(); authenticate=app.state.identity_store.authenticate
    app.state.identity_store.authenticate=lambda token:replace(authenticate(token),permissions=('access.manage',)) if authenticate(token) else None
    return TestClient(app),requests


@pytest.mark.parametrize('status',['saved','already_present','unknown','failed','not_found'])
def test_receipt_keeps_verification_and_excludes_other_fields(status):
    data=normalize_result(receipt(status),'member_note')
    assert data['member_note']['verified']==(status in {'saved','already_present'})
    assert data['sheet_url'] is None and data['stored_verified'] is None
    assert 'secret' not in str(data)


@pytest.mark.parametrize('change',[{'verified':False},{'member_id':None},{'note':None},{'note':'not a dated note'},{'note':'2026-02-30 bad date'},{'candidates':[{'member_id':12,'name':'x','address':'y'}]}])
def test_unverified_or_invalid_saved_result_is_rejected(change):
    value=receipt();value['observations'][0]['result'].update(change)
    with pytest.raises(ValueError):normalize_result(value,'member_note')


def test_case_requires_new_runtime_capability(monkeypatch):
    api,requests=client(monkeypatch,version='1')
    assert api.post('/api/ax768/runs',json=BODY,headers=authenticated_headers()).status_code==409
    assert not requests


def test_admin_csrf_and_explicit_write_case_dispatch(monkeypatch):
    api,requests=client(monkeypatch)
    assert api.post('/api/ax768/runs',json=BODY).status_code==401
    assert api.post('/api/ax768/runs',json=BODY,headers={'Cookie':authenticated_headers()['Cookie']}).status_code==403
    response=api.post('/api/ax768/runs',json=BODY,headers=authenticated_headers())
    assert response.status_code==200 and response.json()['outcome']=='note_saved'
    value=json.loads(requests[0].content)['input']
    assert value=={**BODY,'member_note_case_version':'2'}
    assert 'case_policy' not in value


def test_candidate_is_visible_but_not_a_verified_write():
    value=receipt('needs_confirmation');value['observations'][0]['result']['candidates']=[{'member_id':12,'name':'넥스터_이은경','address':'테스트로 1','mobile':'excluded'}]
    data=normalize_result(value,'member_note')
    assert data['outcome']=='blocked' and not data['member_note']['verified']
    assert 'mobile' not in str(data)
