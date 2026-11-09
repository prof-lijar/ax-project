from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import authenticated_headers, feature_app


def setup_proxy(monkeypatch, *, admin=True, status=200, response_headers=None, body=b'event: result\ndata: ok\n\n'):
    received = []
    async def upstream(request):
        received.append((request, await request.aread()))
        return httpx.Response(status, headers=response_headers or {'Content-Type': 'text/event-stream'},
                              stream=httpx.ByteStream(body))
    original = httpx.AsyncClient
    monkeypatch.setattr('app.integrations.httpx.AsyncClient',
                        lambda **kwargs: original(transport=httpx.MockTransport(upstream), **kwargs))
    app = feature_app()
    authenticate = app.state.identity_store.authenticate
    def authenticate_with_role(token):
        account = authenticate(token)
        return replace(account, permissions=("access.manage",)) if account and admin else account
    app.state.identity_store.authenticate = authenticate_with_role
    return TestClient(app), received


@pytest.mark.parametrize('prefix,upstream,path', [
    ('rag-api', 'http://host.docker.internal:8765', '/rag/v1/embed'),
    ('scout-api', 'http://scout:8091', '/v1/scout/runs'),
    ('scout-scheduler-api', 'http://host.docker.internal:8092', '/v1/scout/schedules'),
    ('weekly-report-bulk-api', 'http://weekly-report-bulk-api:8090', '/v1/jobs'),
    ('agent-server', 'http://agent-server:2024', '/threads'),
])
def test_gateway_authentication_csrf_streaming_and_header_isolation(monkeypatch, prefix, upstream, path):
    client, received = setup_proxy(monkeypatch)
    url = f'/{prefix}{path}?item=one&item=two'
    assert client.post(url).status_code == 401
    assert client.post(url, headers={'Cookie': authenticated_headers()['Cookie']}).status_code == 403
    assert received == []
    headers = {**authenticated_headers(), 'Authorization': 'Bearer must-not-forward',
               'Content-Type': 'application/octet-stream'}
    response = client.post(url, headers=headers, content=b'upload bytes')
    assert response.status_code == 200
    assert response.content == b'event: result\ndata: ok\n\n'
    assert response.headers['content-type'].startswith('text/event-stream')
    request, content = received[0]
    assert str(request.url) == upstream + path + '?item=one&item=two'
    assert content == b'upload bytes'
    for header in ('cookie', 'authorization', 'x-csrf-token', 'origin'):
        assert header not in request.headers


def test_gateway_keeps_downloads_and_rejects_upstream_cookie_injection(monkeypatch):
    client, _ = setup_proxy(monkeypatch, body=b'PKzip', response_headers={
        'content-type': 'application/zip', 'content-disposition': 'attachment; filename=report.zip',
        'set-cookie': 'injected=value', 'access-control-allow-origin': '*',
    })
    response = client.get('/weekly-report-bulk-api/v1/jobs/1/download', headers=authenticated_headers())
    assert response.content == b'PKzip'
    assert response.headers['content-disposition'].endswith('report.zip')
    assert 'set-cookie' not in response.headers and 'access-control-allow-origin' not in response.headers


def test_gateway_does_not_redirect_browser_to_unprotected_upstream(monkeypatch):
    client, _ = setup_proxy(monkeypatch, status=302, response_headers={'location': 'http://private.test/file'})
    response = client.get('/rag-api/rag/v1/data', headers=authenticated_headers())
    assert response.status_code == 502
    assert 'location' not in response.headers


def test_gateway_fails_closed_on_upstream_error(monkeypatch):
    async def offline(request):
        raise httpx.ConnectError('private upstream unavailable', request=request)
    original = httpx.AsyncClient
    monkeypatch.setattr('app.integrations.httpx.AsyncClient',
                        lambda **kwargs: original(transport=httpx.MockTransport(offline), **kwargs))
    response = TestClient(feature_app()).get('/agent-server/ok', headers=authenticated_headers())
    assert response.status_code == 502
    assert 'private upstream' not in response.text


def test_login_cookies_are_isolated_between_frontend_origins():
    from app.identity.config import IdentitySettings
    a = IdentitySettings('unused', 'http://localhost:5173', 'x' * 48, False)
    b = IdentitySettings('unused', 'http://localhost:5174', 'x' * 48, False)
    assert a.cookie_name != b.cookie_name


def test_upstream_unauthorized_is_not_reported_as_an_expired_nexgent_login(monkeypatch):
    client, _ = setup_proxy(monkeypatch, status=401)
    assert client.get('/agent-server/ok', headers=authenticated_headers()).status_code == 502


@pytest.mark.parametrize("prefix", ["rag-api", "scout-api", "scout-scheduler-api", "weekly-report-bulk-api"])
@pytest.mark.parametrize("method", ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("admin", [False, True])
def test_restricted_gateways_require_administrator_for_every_operation(monkeypatch, prefix, method, admin):
    client, received = setup_proxy(monkeypatch, admin=admin)
    response = client.request(method, f"/{prefix}/v1/resource", headers=authenticated_headers())
    assert response.status_code == (200 if admin else 403)
    assert len(received) == (1 if admin else 0)
    if not admin and method != "HEAD":
        assert response.json() == {"error": {"code": "permission_denied"}}


@pytest.mark.parametrize("method,path", [
    ("POST", "threads"), ("POST", "runs/wait"),
    ("GET", "threads/example/state"), ("POST", "assistants/search"),
    ("POST", "ok"),
])
def test_member_cannot_bypass_agent_workspace_permissions(monkeypatch, method, path):
    client, received = setup_proxy(monkeypatch, admin=False)
    response = client.request(method, f"/agent-server/{path}", headers=authenticated_headers(), json={})
    assert response.status_code == 403
    assert received == []
    assert client.get("/agent-server/ok", headers=authenticated_headers()).status_code == 200


def test_revoked_admin_access_is_checked_again_on_the_next_request(monkeypatch):
    client, received = setup_proxy(monkeypatch)
    assert client.get("/rag-api/rag/v1/data", headers=authenticated_headers()).status_code == 200
    from conftest import FeatureIdentityStore
    client.app.state.identity_store = FeatureIdentityStore()
    assert client.get("/rag-api/rag/v1/data", headers=authenticated_headers()).status_code == 403
    assert len(received) == 1
