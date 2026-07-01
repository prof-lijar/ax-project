import pytest

from app.core.settings import Settings
from app.nextcloud.client import NextcloudClient, NextcloudError


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("NC_URL", "https://nextor-ai-02.tail8e1643.ts.net")
    monkeypatch.setenv("NC_USER", "lijar")
    monkeypatch.setenv("NC_PASS", "secret")
    monkeypatch.setenv("NC_VERIFY_SSL", "false")
    return Settings()


def test_webdav_url_encodes_path_segments(settings):
    client = NextcloudClient(settings)

    url = client._absolute_webdav_url("AX Project/agent output.md")

    assert url == (
        "https://nextor-ai-02.tail8e1643.ts.net"
        "/remote.php/dav/files/lijar/AX%20Project/agent%20output.md"
    )


def test_clean_path_rejects_traversal(settings):
    client = NextcloudClient(settings)

    with pytest.raises(NextcloudError):
        client._clean_path("../Readme.md")


def test_parse_propfind_skips_requested_root(settings):
    client = NextcloudClient(settings)
    xml = b"""<?xml version="1.0"?>
    <d:multistatus xmlns:d="DAV:">
      <d:response>
        <d:href>/remote.php/dav/files/lijar/AX%20Project/</d:href>
        <d:propstat><d:prop><d:resourcetype><d:collection /></d:resourcetype></d:prop></d:propstat>
      </d:response>
      <d:response>
        <d:href>/remote.php/dav/files/lijar/AX%20Project/agent-test.md</d:href>
        <d:propstat>
          <d:prop>
            <d:getcontentlength>19</d:getcontentlength>
            <d:getcontenttype>text/markdown</d:getcontenttype>
            <d:getetag>"abc"</d:getetag>
            <d:getlastmodified>Wed, 01 Jul 2026 01:00:00 GMT</d:getlastmodified>
            <d:resourcetype />
          </d:prop>
        </d:propstat>
      </d:response>
    </d:multistatus>
    """

    items = client._parse_propfind(xml, root_path="AX Project")

    assert len(items) == 1
    assert items[0].path == "AX Project/agent-test.md"
    assert items[0].name == "agent-test.md"
    assert items[0].is_directory is False
    assert items[0].size == 19

