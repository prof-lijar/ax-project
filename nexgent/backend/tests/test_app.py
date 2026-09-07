import asyncio

import httpx


async def _request(app, method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, **kwargs)


def test_app_imports_with_routes(monkeypatch):
    monkeypatch.setenv("NC_URL", "https://nextor-ai-02.tail8e1643.ts.net")
    monkeypatch.setenv("NC_USER", "lijar")
    monkeypatch.setenv("NC_PASS", "secret")

    from app.main import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/health" in paths
    assert "/api/chat/stream" in paths
    assert "/api/rag/chat/stream" in paths
    assert "/api/nextcloud/files" in paths
    assert "/api/nextcloud/files/content" in paths
    assert "/api/nextcloud/files/preview" in paths
    assert "/api/nextcloud/capabilities" in paths


def test_health_check_does_not_require_integration_credentials(monkeypatch):
    monkeypatch.delenv("NC_URL", raising=False)
    monkeypatch.delenv("NC_USER", raising=False)
    monkeypatch.delenv("NC_PASS", raising=False)

    from app.main import create_app

    response = asyncio.run(_request(create_app(), "GET", "/health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_origin_regex_is_configurable(monkeypatch):
    monkeypatch.setenv(
        "NEXGENT_CORS_ORIGIN_REGEX",
        r"^https?://[^/]+:5173$",
    )

    from app.main import create_app

    response = asyncio.run(
        _request(
            create_app(),
            "OPTIONS",
            "/health",
            headers={
                "Origin": "http://dev-machine:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://dev-machine:5173"


def test_cors_regex_uses_compose_frontend_port(monkeypatch):
    monkeypatch.delenv("NEXGENT_CORS_ORIGIN_REGEX", raising=False)
    monkeypatch.setenv("NEXGENT_CORS_FRONTEND_PORT", "5174")

    from app.main import create_app

    response = asyncio.run(
        _request(
            create_app(),
            "OPTIONS",
            "/health",
            headers={
                "Origin": "http://dev-machine:5174",
                "Access-Control-Request-Method": "GET",
            },
        )
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://dev-machine:5174"


def test_content_disposition_supports_unicode_filename():
    from app.nextcloud.router import _content_disposition

    header = _content_disposition(
        "inline",
        "안심지키미_AX_Problem_Statements_v0.1.pdf",
    )

    header.encode("latin-1")
    assert 'filename="_AX_Problem_Statements_v0.1.pdf"' in header
    assert (
        "filename*=UTF-8''%EC%95%88%EC%8B%AC%EC%A7%80%ED%82%A4%EB%AF%B8_AX_Problem_Statements_v0.1.pdf"
        in header
    )
