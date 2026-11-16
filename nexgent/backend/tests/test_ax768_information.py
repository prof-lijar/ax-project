from copy import deepcopy
from dataclasses import replace
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from app.ax768_information import ASSISTANT_ID, GRAPH, normalize
from conftest import feature_app, authenticated_headers

PATH='/api/ax768/workflow/information-runs'
BODY={'workflow_id':'information_update','message':'김하늘 생년월일 380215로 수정'}
RECEIPT={'status':'updated','reason':'확인','rows':[6],'changes':['생년월일: 380215'],'verified':True}
RESULT={'region':'영덕','status':'completed','response':'완료','receipts':{key:deepcopy(RECEIPT) for key in ('roster','as_update','member_note')}}


def setup(monkeypatch,result=None,version='2',admin=True):
    requests=[]
    async def upstream(request):
        requests.append(request)
        if request.method=='GET':
            assert request.url.path==f'/assistants/{ASSISTANT_ID}/schemas'
            return httpx.Response(200,json={'input_schema':{'properties':{'information_version':{'const':version}}}})
        return httpx.Response(200,json=result if result is not None else {**RESULT,'context':{'private':'omitted'}})
    original=httpx.AsyncClient
    monkeypatch.setattr('app.ax768_information.httpx.AsyncClient',lambda **kw:original(transport=httpx.MockTransport(upstream),**kw))
    monkeypatch.setenv('AX_AGENT_SERVER_URL','http://agent:2024')
    app=feature_app();authenticate=app.state.identity_store.authenticate
    app.state.identity_store.authenticate=lambda token:replace(authenticate(token),permissions=('access.manage',)) if authenticate(token) and admin else authenticate(token)
    return TestClient(app),requests


def test_dispatch_is_fixed_and_returns_only_receipts(monkeypatch):
    client,requests=setup(monkeypatch)
    response=client.post(PATH,headers=authenticated_headers(),json=BODY)
    assert response.status_code==200
    assert 'context' not in response.json()
    sent=json.loads(requests[1].content)
    assert sent['assistant_id']==GRAPH
    assert sent['input']=={'message':BODY['message'],'information_version':'2'}
    assert sent['on_disconnect']=='continue' and sent['on_completion']=='delete'


@pytest.mark.parametrize('admin',[True,False])
def test_permissions_and_csrf_precede_dispatch(monkeypatch,admin):
    client,requests=setup(monkeypatch,admin=admin)
    assert client.post(PATH,json=BODY).status_code==401
    assert client.post(PATH,json=BODY,headers={'Cookie':authenticated_headers()['Cookie']}).status_code==403
    if not admin:
        assert client.post(PATH,json=BODY,headers=authenticated_headers()).status_code==403
    assert requests==[]


@pytest.mark.parametrize('change',[{'region':''},{'region':'서울'},{'workflow_id':'device_adjustment_power'},{'message':' '},{'message':'x'*8001},{'sheet_id':12}])
def test_invalid_input_never_dispatches(monkeypatch,change):
    client,requests=setup(monkeypatch)
    assert client.post(PATH,json={**BODY,**change},headers=authenticated_headers()).status_code==422
    assert requests==[]


def test_old_server_gate(monkeypatch):
    client,requests=setup(monkeypatch,version='1')
    assert client.post(PATH,json=BODY,headers=authenticated_headers()).status_code==409
    assert len(requests)==1


def test_receipts_enforce_order_and_verification():
    result=deepcopy(RESULT)
    result['receipts']['as_update']={'status':'skipped','reason':'없음','rows':[],'changes':[],'verified':True}
    assert normalize(result)['status']=='completed'
    for key in ('roster','as_update','member_note'):
        broken=deepcopy(RESULT);broken['receipts'][key]['verified']=False
        with pytest.raises(ValueError): normalize(broken)
    broken=deepcopy(RESULT);broken['receipts']['roster']['rows']=[6,7]
    with pytest.raises(ValueError): normalize(broken)
    broken=deepcopy(RESULT);broken['receipts']['roster']['rows']=[True]
    with pytest.raises(ValueError): normalize(broken)
    broken=deepcopy(RESULT);broken['receipts']['as_update']['status']='unknown'
    with pytest.raises(ValueError): normalize(broken)


def test_bad_upstream_never_claims_success(monkeypatch):
    client,_=setup(monkeypatch,result={'status':'completed','response':'done','receipts':{}})
    response=client.post(PATH,json=BODY,headers=authenticated_headers())
    assert response.status_code==502


def test_resolved_region_required_only_after_target_selection():
    result=deepcopy(RESULT);result['region']=None
    with pytest.raises(ValueError): normalize(result)
    result={'status':'blocked','response':'not found','region':None,'receipts':{key:{'status':'skipped','reason':'not run','rows':[],'changes':[],'verified':False} for key in RESULT['receipts']}}
    assert normalize(result)['region'] is None
