"""Native Block Kit input validation and complete accessible delivery."""
import copy
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.notifications.schemas import SlackNotification
from app.notifications.slack import SlackClient, render_message
from conftest import authenticated_headers
from test_notifications import api, settings, store  # noqa: F401


def native_body():
    return {'text': 'Summary', 'blocks': [
        {'type': 'header', 'text': {'type': 'plain_text', 'text': '주간 리포트'}},
        {'type': 'section', 'text': {'type': 'mrkdwn', 'text': '*Complete* <!channel> <@U123>'}},
        {'type': 'context', 'elements': [{'type': 'plain_text', 'text': '09/21~09/27'}]},
        {'type': 'divider'},
        {'type': 'table', 'column_settings': [{'align': 'left'}, {'align': 'right'}],
         'rows': [[{'type': 'raw_text', 'text': '지역'}, {'type': 'raw_text', 'text': '누락'}],
                  [{'type': 'raw_text', 'text': '광명'}, {'type': 'raw_text', 'text': '1'}]]},
        {'type': 'section', 'text': {'type': 'plain_text', 'text': '집계 기준\n모든 정보 유지'}},
    ]}


def test_native_blocks_api_round_trip_and_rendering(api, store, settings):
    body = native_body()
    headers = {**authenticated_headers(), 'Idempotency-Key': 'native-blocks'}
    response = api.post('/api/notifications/slack', json=body, headers=headers)
    assert response.status_code == 202
    assert api.post('/api/notifications/slack', json=body, headers=headers).json()['id'] == response.json()['id']
    job = store.claim(settings)
    original = copy.deepcopy(job['payload'])
    rendered = render_message(job)
    assert [block['type'] for block in rendered['blocks']] == [block['type'] for block in body['blocks']]
    assert job['payload'] == original
    assert rendered['blocks'][1]['text']['text'] == '*Complete* &lt;!channel&gt; &lt;@U123&gt;'
    assert rendered['blocks'][1]['text']['verbatim'] is True
    assert 'block_id' not in rendered['blocks'][0]
    assert 'fields' not in rendered['blocks'][1]
    assert 'WARNING' not in rendered['text']
    assert '광명 | 1' in rendered['text'] and '모든 정보 유지' in rendered['text']
    assert '<!channel>' not in rendered['text']


def test_native_blocks_are_sent_unchanged_structurally(settings):
    import asyncio
    parsed = SlackNotification.model_validate(native_body())
    job = {'id': str(uuid4()), 'channel_id': 'C0123456789', 'payload': parsed.model_dump(mode='json')}
    expected = render_message(job)
    def handler(request):
        import json
        assert json.loads(request.content) == expected
        return httpx.Response(200, json={'ok': True, 'ts': '1234567890.123456'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await SlackClient(client, settings).send(job) == '1234567890.123456'
    asyncio.run(run())


@pytest.mark.parametrize('blocks', [
    [{'type': 'unknown'}], [{'type': 'divider'}] * 51,
    [{'type': 'header', 'text': {'type': 'mrkdwn', 'text': '*bad*'}}],
    [{'type': 'header', 'text': {'type': 'plain_text', 'text': 'x' * 151}}],
    [{'type': 'section'}],
    [{'type': 'section', 'fields': [{'type': 'plain_text', 'text': 'x' * 2001}]}],
    [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': '&' * 601}}],
    [{'type': 'context', 'elements': []}],
    [{'type': 'table', 'rows': [[]]}],
    [{'type': 'table', 'rows': [[{'type': 'raw_text', 'text': 'a'}], []]}],
    [{'type': 'divider', 'block_id': 'same'}, {'type': 'divider', 'block_id': 'same'}],
    [{'type': 'section', 'text': {'type': 'plain_text', 'text': 'x' * 3000}}] * 11,
    [{'type': 'table', 'rows': [[{'type': 'raw_text', 'text': 'a'}]]}] * 2,
])
def test_invalid_native_blocks_are_rejected(blocks):
    with pytest.raises(ValidationError):
        SlackNotification(text='test', blocks=blocks)


@pytest.mark.parametrize('extra', [{'title': 'hidden title'}, {'footer': 'hidden footer'},
    {'fields': [{'name': 'hidden', 'value': 'hidden'}]}, {'url': 'https://example.com'},
    {'table': {'columns': ['hidden'], 'rows': [['hidden']]}}])
def test_mixed_layout_rejected_instead_of_discarding_information(extra):
    with pytest.raises(ValidationError):
        SlackNotification(**{**native_body(), **extra})


def test_native_validation_is_enforced_at_api(api):
    response = api.post('/api/notifications/slack', json={'text': 'test', 'blocks': [{'type': 'unknown'}]},
                        headers={**authenticated_headers(), 'Idempotency-Key': 'bad-native'})
    assert response.status_code == 422
