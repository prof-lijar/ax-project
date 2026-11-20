import json
from itertools import permutations

import pytest

from app.ax768_dispatch import route_message
from conftest import authenticated_headers
from test_ax768_workflow import payload, setup

PATH = '/api/ax768/runs'


@pytest.mark.parametrize('fields', list(permutations(['위치조정', '김순옥', '울진북로 164'])))
def test_auto_dispatch_any_order_and_server_template(monkeypatch, fields):
    client, requests = setup(monkeypatch)
    response = client.post(PATH, json={'message': '/'.join(fields)}, headers=authenticated_headers())
    assert response.status_code == 200
    assert response.json()['api_version'] == '1'
    assert response.json()['verified'] is True
    assert response.json()['workflow_id'] == 'device_adjustment_power'
    assert response.json()['response'] == '[자동 확인]\n김순옥님 기기 위치변경 후 기기신호 확인 완료입니다.\n내용 기재해두었습니다.\n감사합니다. :)'
    assert json.loads(requests[0].content)['input']['message'] == '울진북로 164 김순옥님 기기위치조정 신호확인요.'
    assert len(requests) == 1


def test_disconnected_template(monkeypatch):
    result = payload()
    result.update(member_note=None, status='disconnected', as_lookup={'status':'skipped'}, as_update={'status':'skipped','verified':False})
    result['signal'].update(status='disconnected',connected=False,fresh=False)
    client, requests = setup(monkeypatch, result=result)
    response = client.post(PATH, json={'message':'위치조정/김순옥/울진북로 164'}, headers=authenticated_headers())
    assert response.status_code == 200
    assert response.json()['response'] == '[자동 확인]\n김순옥님 신규설치 기기신호가 아직 확인되지 않습니다.\n기기 전원 및 설치 위치 확인 부탁드립니다. '
    assert len(requests) == 1


@pytest.mark.parametrize('message', [
    '안녕하세요', '위치조정/김순옥', '김순옥/울진북로 164',
    '신규설치/김순옥/울진북로 164', '위치조정/전원연결/김순옥/울진북로 164',
    '위치조정 취소/김순옥/울진북로 164', '위치조정/김순옥/울진북로 164 취소',
    '예시: 위치조정/김순옥/울진북로 164',
])
def test_ambiguous_unsupported_or_nonrequest_does_not_execute(monkeypatch, message):
    client, requests = setup(monkeypatch)
    response = client.post(PATH, json={'message':message}, headers=authenticated_headers())
    assert response.status_code == 200
    assert response.json()['status'] == 'needs_confirmation'
    assert not requests


def test_user_example_and_aliases():
    assert route_message('이영희/광명시 OO동 OO로 56/위치 조정') == (
        'device_adjustment_power', '광명시 OO동 OO로 56 이영희님 기기위치조정 신호확인요.')
    assert route_message('전원연결/이영희/광명시 OO로56')[0] == 'device_adjustment_power'
    assert route_message('정보수정/이영희/전화번호 010-1234-5678로 변경')[0] == 'information_update'


def test_authorization_and_validation(monkeypatch):
    client, requests = setup(monkeypatch)
    body = {'message':'위치조정/김순옥/울진북로 164'}
    assert client.post(PATH,json=body).status_code == 401
    assert client.post(PATH,json=body,headers={'Cookie': authenticated_headers()['Cookie']}).status_code == 403
    for bad in [{**body,'workflow_id':'other'}, {**body,'confirmed_name':'김영호'}, {**body,'url':'https://other'}, {'message':' '}]:
        assert client.post(PATH,json=bad,headers=authenticated_headers()).status_code == 422
    assert not requests


def test_selected_web_workflow_keeps_receipts(monkeypatch):
    client, requests = setup(monkeypatch)
    response = client.post(PATH,json={'workflow_id':'device_adjustment_power','message':'울진북로 164 김순옥님 신호확인요.'},headers=authenticated_headers())
    assert response.status_code == 200
    assert response.json()['member_note']['verified'] is True
    assert len(requests) == 1


def test_invalid_receipts_never_emit_success(monkeypatch):
    result=payload(); result['member_note']['verified']=False
    client, requests=setup(monkeypatch,result=result)
    assert client.post(PATH,json={'message':'위치조정/김순옥/울진북로 164'},headers=authenticated_headers()).status_code == 502
    assert len(requests) == 1


@pytest.mark.parametrize("selection", ["auto", "information_update"])
def test_information_dispatch(monkeypatch, selection):
    from test_ax768_information import setup as information_setup
    client, requests = information_setup(monkeypatch)
    response = client.post(PATH, json={'workflow_id':selection,'message':'정보수정/김순옥/생년월일 380215로 수정'},headers=authenticated_headers())
    assert response.status_code == 200
    assert response.json()['workflow_id'] == 'information_update'
    assert response.json()['response'].startswith('[자동 확인]\n')
    assert len(requests) == 2


@pytest.mark.parametrize('fields', list(permutations(['위치조정', '김순옥', '울진북로 164'])))
def test_selected_device_workflow_accepts_capture_field_order(monkeypatch, fields):
    client, requests = setup(monkeypatch)
    response = client.post(PATH, json={
        'workflow_id': 'device_adjustment_power', 'message': '/'.join(fields),
    }, headers=authenticated_headers())
    assert response.status_code == 200
    assert response.json()['workflow_id'] == 'device_adjustment_power'
    assert response.json()['verified'] is True
    assert len(requests) == 1
    assert json.loads(requests[0].content)['input']['message'] == '울진북로 164 김순옥님 기기위치조정 신호확인요.'


@pytest.mark.parametrize('message', [
    '정보수정/김순옥/위치조정 관련 전화번호 변경',
    '위치조정/김순옥',
    '위치조정 취소/김순옥/울진북로 164',
    '위치조정/김순옥/울진북로 164 취소',
    '위치조정/정보수정/김순옥/울진북로 164',
])
def test_selected_device_never_dispatches_other_or_ambiguous_slash_workflow(monkeypatch, message):
    client, requests = setup(monkeypatch)
    response = client.post(PATH, json={
        'workflow_id': 'device_adjustment_power', 'message': message,
    }, headers=authenticated_headers())
    assert response.status_code == 200
    assert response.json()['status'] == 'needs_confirmation'
    assert not requests


@pytest.mark.parametrize('fields', list(permutations(['전원연결', '박철수', '울진군 OO면 OO길 78'])))
@pytest.mark.parametrize('connected', [True, False])
def test_explicit_power_action_routes_and_returns_exact_template(monkeypatch, fields, connected):
    result = payload()
    for key in ('roster', 'parsed', 'member_note', 'as_lookup'):
        result[key].update(name='박철수', address='OO길 78')
    result['parsed']['lookup_name'] = '박철수'
    result['member_note']['note'] = '2026-11-04 [현지관리자 방문] 전원연결'
    if not connected:
        result.update(member_note=None, status='disconnected', as_lookup={'status':'skipped'}, as_update={'status':'skipped','verified':False})
        result['signal'].update(status='disconnected', connected=False, fresh=False)
    client, requests = setup(monkeypatch, result=result)
    response = client.post(PATH, json={
        'workflow_id': 'device_adjustment_power', 'action': '전원연결',
        'message': '/'.join(fields) + ' ', 'confirmed_name': None,
    }, headers=authenticated_headers())
    assert response.status_code == 200
    assert response.json()['verified'] is connected
    assert response.json()['workflow_id'] == 'device_adjustment_power'
    expected = ('[자동 확인]\n박철수님 기기 전원연결 후 기기신호 확인 완료입니다.\n내용 기재해두었습니다.\n감사합니다. :)'
                if connected else '[자동 확인]\n박철수님 신규설치 기기신호가 아직 확인되지 않습니다.\n기기 전원 및 설치 위치 확인 부탁드립니다. ')
    assert response.json()['response'] == expected
    assert len(requests) == 1
    assert json.loads(requests[0].content)['input']['message'] == '울진군 OO면 OO길 78 박철수님 전원연결 신호확인요.'


@pytest.mark.parametrize('action,message', [
    ('기기위치조정', '위치조정/김순옥/울진북로 164'),
    ('전원연결', '울진북로 164 김순옥님 전원연결 신호확인요.'),
])
def test_specific_action_matches_source(monkeypatch, action, message):
    result = payload()
    result['member_note']['note'] = '2026-11-04 [현지관리자 방문] ' + action
    client, requests = setup(monkeypatch, result=result)
    response = client.post(PATH, json={
        'workflow_id': 'device_adjustment_power', 'action': action, 'message': message,
    }, headers=authenticated_headers())
    assert response.status_code == 200
    assert response.json()['status'] == 'completed'
    assert len(requests) == 1


@pytest.mark.parametrize('action,message', [
    ('전원연결', '위치조정/김순옥/울진북로 164'),
    ('기기위치조정', '전원연결/김순옥/울진북로 164'),
    ('전원연결', '울진북로 164 김순옥님 신호확인요.'),
    ('전원연결', '울진북로 164 김순옥님 기기위치조정 및 전원연결 신호확인요.'),
    ('전원연결', '전원연결 취소/김순옥/울진북로 164'),
])
def test_specific_action_never_overrides_source(monkeypatch, action, message):
    client, requests = setup(monkeypatch)
    response = client.post(PATH, json={
        'workflow_id': 'device_adjustment_power', 'action': action, 'message': message,
    }, headers=authenticated_headers())
    assert response.status_code == 200
    assert response.json()['status'] == 'needs_confirmation'
    assert not requests


def test_invalid_action_or_wrong_workflow_rejected(monkeypatch):
    client, requests = setup(monkeypatch)
    for body in [
        {'workflow_id':'device_adjustment_power', 'action':'신규설치', 'message':'전원연결/김순옥/울진북로 164'},
        {'workflow_id':'information_update', 'action':'전원연결', 'message':'정보수정/김순옥/전화번호 변경'},
    ]:
        assert client.post(PATH, json=body, headers=authenticated_headers()).status_code == 422
    assert not requests



def test_completed_receipt_must_match_explicit_action(monkeypatch):
    # The default fixture proves location adjustment, not power connection.
    client, requests = setup(monkeypatch)
    response = client.post(PATH, json={
        'workflow_id':'device_adjustment_power', 'action':'전원연결',
        'message':'전원연결/김순옥/울진북로 164',
    }, headers=authenticated_headers())
    assert response.status_code == 502
    assert len(requests) == 1


@pytest.mark.parametrize('keyword,action', [('위치조정', '기기위치조정'), ('전원연결', '전원연결')])
@pytest.mark.parametrize('order', list(permutations(range(3))))
@pytest.mark.parametrize('selection', ['auto', 'device_adjustment_power'])
@pytest.mark.parametrize('structured', [False, True])
def test_registered_underscore_name_reaches_device_workflow(monkeypatch, keyword, action, order, selection, structured):
    fields = [keyword, '넥스터_이은경', '헌릉로8길58']
    message = '/'.join(fields[index] for index in order)
    result = payload()
    for key in ('roster', 'parsed', 'member_note', 'as_lookup'):
        result[key].update(name='넥스터_이은경', address='헌릉로8길58')
    result['parsed']['lookup_name'] = '넥스터_이은경'
    result['member_note']['note'] = '2026-11-04 [현지관리자 방문] ' + action
    client, requests = setup(monkeypatch, result=result)
    response = client.post(PATH, json={
        'workflow_id': selection, 'action': action, 'message': message,
        **({'name': '넥스터_이은경', 'address': '헌릉로8길58', 'action_text': keyword} if structured else {}),
    }, headers=authenticated_headers())
    assert response.status_code == 200
    assert response.json()['status'] == 'completed'
    assert response.json()['verified'] is True
    assert response.json()['response'].startswith('[자동 확인]\n넥스터_이은경님 ')
    assert len(requests) == 1
    assert json.loads(requests[0].content)['input']['message'] == f'헌릉로8길58 넥스터_이은경님 {action} 신호확인요.'


@pytest.mark.parametrize('name', ['_이은경', '넥스터_', '넥스터__이은경', '넥스터_이은경;취소', '넥스터_이은경/김영희'])
def test_malformed_underscore_name_still_does_not_dispatch(name):
    assert route_message(f'위치조정/{name}/헌릉로8길58') is None


@pytest.mark.parametrize('change', [
    {'name': '이은경'},
    {'name': '김영희'},
    {'address': '헌릉로8길59'},
    {'action': '전원연결'},
    {'message': '위치조정/넥스터_이은경/헌릉로8길58 취소'},
    {'message': '위치조정 취소/넥스터_이은경/헌릉로8길58'},
])
def test_structured_fields_cannot_change_source_identity_or_omit_cancellation(monkeypatch, change):
    client, requests = setup(monkeypatch)
    body = {
        'workflow_id': 'device_adjustment_power', 'action': '기기위치조정',
        'name': '넥스터_이은경', 'address': '헌릉로8길58', 'action_text': '위치조정',
        'message': '위치조정/넥스터_이은경/헌릉로8길58',
    }
    response = client.post(PATH, json={**body, **change}, headers=authenticated_headers())
    assert response.status_code == 200
    assert response.json()['status'] == 'needs_confirmation'
    assert not requests


@pytest.mark.parametrize('change', [
    {'name': None}, {'address': None}, {'action': None}, {'workflow_id': 'information_update'},
])
def test_partial_or_wrong_structured_contract_is_rejected(monkeypatch, change):
    client, requests = setup(monkeypatch)
    body = {
        'workflow_id': 'device_adjustment_power', 'action': '기기위치조정',
        'name': '넥스터_이은경', 'address': '헌릉로8길58', 'action_text': '위치조정',
        'message': '위치조정/넥스터_이은경/헌릉로8길58',
    }
    assert client.post(PATH, json={**body, **change}, headers=authenticated_headers()).status_code == 422
    assert not requests


@pytest.mark.parametrize('message,evidence,action', [
    ('헌릉로8길58 넥스터_이은경님 기기를 다른 곳으로 옮겼습니다', '기기를 다른 곳으로 옮겼습니다', '기기위치조정'),
    ('넥스터_이은경님 / 헌릉로8길58 / 전기를 다시 꽂았습니다', '전기를 다시 꽂았습니다', '전원연결'),
])
def test_semantic_structured_request_needs_no_exact_keyword_or_field_order(monkeypatch, message, evidence, action):
    result = payload()
    for key in ('roster', 'parsed', 'member_note', 'as_lookup'):
        result[key].update(name='넥스터_이은경', address='헌릉로8길58')
    result['parsed']['lookup_name'] = '넥스터_이은경'
    result['member_note']['note'] = '2026-11-04 [현지관리자 방문] ' + action
    client, requests = setup(monkeypatch, result=result)
    response = client.post(PATH, json={
        'workflow_id': 'device_adjustment_power', 'action': action, 'action_text': evidence,
        'name': '넥스터_이은경', 'address': '헌릉로8길58', 'message': message,
    }, headers=authenticated_headers())
    assert response.status_code == 200
    assert response.json()['status'] == 'completed'
    assert len(requests) == 1
    assert json.loads(requests[0].content)['input']['message'] == f'헌릉로8길58 넥스터_이은경님 {action} 신호확인요.'
