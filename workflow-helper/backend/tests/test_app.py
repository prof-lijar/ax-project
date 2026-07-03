def test_app_imports_with_routes(monkeypatch):
    monkeypatch.setenv("NC_URL", "https://nextor-ai-02.tail8e1643.ts.net")
    monkeypatch.setenv("NC_USER", "lijar")
    monkeypatch.setenv("NC_PASS", "secret")

    from app.main import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/nextcloud/files" in paths
    assert "/api/nextcloud/files/content" in paths
    assert "/api/nextcloud/files/preview" in paths
    assert "/api/nextcloud/capabilities" in paths


def test_content_disposition_supports_unicode_filename():
    from app.nextcloud.router import _content_disposition

    header = _content_disposition(
        "inline",
        "안심지키미_AX_Problem_Statements_v0.1.pdf",
    )

    header.encode("latin-1")
    assert 'filename="_AX_Problem_Statements_v0.1.pdf"' in header
    assert "filename*=UTF-8''%EC%95%88%EC%8B%AC%EC%A7%80%ED%82%A4%EB%AF%B8_AX_Problem_Statements_v0.1.pdf" in header
