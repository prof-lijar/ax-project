def test_app_imports_with_routes(monkeypatch):
    monkeypatch.setenv("NC_URL", "https://nextor-ai-02.tail8e1643.ts.net")
    monkeypatch.setenv("NC_USER", "lijar")
    monkeypatch.setenv("NC_PASS", "secret")

    from app.main import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/nextcloud/files" in paths
    assert "/api/nextcloud/files/content" in paths
    assert "/api/nextcloud/capabilities" in paths
