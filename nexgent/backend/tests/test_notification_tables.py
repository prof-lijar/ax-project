"""Native Slack table contracts and backwards-compatible queue submission."""
from hashlib import sha256
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.notifications.schemas import SlackNotification
from app.notifications.slack import render_message
from conftest import authenticated_headers
from test_notifications import api, settings, store  # noqa: F401 - shared fixtures


def table_payload():
    return {
        'title': '주간 리포트 저장 현황', 'text': '지난주 누락 1명',
        'severity': 'warning', 'locale': 'ko',
        'table': {
            'columns': ['지역', '가입자', '성공', '누락', '누락률'],
            'rows': [['전체', '6,601', '6,600', '1', '0.02%'], ['광명', '451', '450', '1', '0.22%']],
            'align': ['left', 'right', 'right', 'right', 'right'],
        },
        'footer': '집계 기준\n• 현재 가입자 기준\n• 누락 = 리포트 없음',
    }


def test_native_table_submission_persists_and_replays(api, store, settings):
    headers = {**authenticated_headers(), 'Idempotency-Key': 'native-table'}
    first = api.post('/api/notifications/slack', headers=headers, json=table_payload())
    assert first.status_code == 202
    again = api.post('/api/notifications/slack', headers=headers, json=table_payload())
    assert again.json()['id'] == first.json()['id']
    changed = table_payload()
    changed['table']['rows'][0][2] = '6,599'
    assert api.post('/api/notifications/slack', headers=headers, json=changed).status_code == 409
    job = store.claim(settings)
    rendered = render_message(job)
    table = next(block for block in rendered['blocks'] if block['type'] == 'table')
    assert len(table['rows']) == 3
    assert table['rows'][1][2] == {'type': 'raw_text', 'text': '6,600'}
    assert all(column['align'] == 'right' for column in table['column_settings'][1:])
    assert '확인 필요' in rendered['text'] and 'WARNING' not in rendered['text']
    assert rendered['blocks'][-1]['text']['text'] == table_payload()['footer']
    for row in table_payload()['table']['rows']:
        assert ' | '.join(row) in rendered['text']


@pytest.mark.parametrize('table', [
    {'columns': [], 'rows': [['x']]},
    {'columns': ['a'], 'rows': []},
    {'columns': ['a', 'b'], 'rows': [['x']]},
    {'columns': ['a'], 'rows': [['x']], 'align': ['left', 'right']},
    {'columns': ['a'], 'rows': [['x']], 'align': ['invalid']},
    {'columns': ['a'] * 21, 'rows': [['x'] * 21]},
    {'columns': ['a'], 'rows': [['x']] * 100},
    {'columns': ['a'], 'rows': [['x' * 1001]]},
    {'columns': ['a'] * 20, 'rows': [['x' * 1000] * 20]},
])
def test_invalid_tables_fail_validation(table):
    with pytest.raises(ValidationError):
        SlackNotification(text='test', table=table)


def test_tables_at_slack_limits_and_literal_mentions():
    # 100 rows including header; all cells are text, never parsed mentions/links.
    parsed = SlackNotification(text='<!channel>', table={'columns': ['Heading'], 'rows': [['<@U123> & text']] * 99}, footer='tail')
    rendered = render_message({'id': str(uuid4()), 'channel_id': 'C0123456789', 'payload': parsed.model_dump(mode='json')})
    table = next(block for block in rendered['blocks'] if block['type'] == 'table')
    assert len(table['rows']) == 100
    assert all(cell['type'] == 'raw_text' for row in table['rows'] for cell in row)
    assert '<!channel>' not in rendered['text'] and '<@U123>' not in rendered['text']
    assert rendered['parse'] == 'none' and rendered['mrkdwn'] is False


def test_exact_table_character_budget():
    SlackNotification(text='test', table={'columns': ['h' * 1000], 'rows': [['x' * 1000]] * 9})
    with pytest.raises(ValidationError):
        SlackNotification(text='test', table={'columns': ['h' * 1000], 'rows': [['x' * 1000]] * 9 + [['x']]})


def test_legacy_fingerprint_is_preserved(api, store, settings):
    legacy = {'destination': 'default', 'text': 'Old notification', 'title': None,
              'severity': 'info', 'fields': [], 'url': None, 'thread_ts': None}
    fingerprint = sha256(json.dumps(legacy, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    # Seed the exact normalized shape used before the schema extension.
    old = store.enqueue('service:notifications', 'legacy', fingerprint, 'default', settings.channels['default'], legacy)
    response = api.post('/api/notifications/slack', json={'text': 'Old notification'},
                        headers={'Authorization': 'Bearer ' + settings.service_token.get_secret_value(), 'Idempotency-Key': 'legacy'})
    assert response.status_code == 202
    assert response.json()['id'] == old['id']


def test_bad_table_is_rejected_by_api(api):
    body = table_payload()
    body['table']['rows'][0].pop()
    response = api.post('/api/notifications/slack', json=body,
                        headers={**authenticated_headers(), 'Idempotency-Key': 'invalid-table'})
    assert response.status_code == 422
