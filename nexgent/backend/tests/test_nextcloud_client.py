import asyncio

import httpx
import pytest

from app.core.settings import Settings
from app.nextcloud.client import DownloadedFile, NextcloudClient, NextcloudError


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
        "/remote.php/dav/files/lijar/Slack/AX%20Project/agent%20output.md"
    )


def test_clean_path_rejects_traversal(settings):
    client = NextcloudClient(settings)

    with pytest.raises(NextcloudError):
        client._clean_path("../Readme.md")


def test_ca_bundle_overrides_verify_ssl(monkeypatch):
    monkeypatch.setenv("NC_URL", "https://nextor-ai-02.tail8e1643.ts.net")
    monkeypatch.setenv("NC_USER", "lijar")
    monkeypatch.setenv("NC_PASS", "secret")
    monkeypatch.setenv("NC_VERIFY_SSL", "false")
    monkeypatch.setenv("NC_CA_BUNDLE", "/etc/ssl/private-nextcloud-ca.pem")

    assert Settings().nextcloud_verify_ssl == "/etc/ssl/private-nextcloud-ca.pem"


def test_request_errors_are_nextcloud_errors(settings, monkeypatch):
    class FailingAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def request(self, method, url, **kwargs):
            raise httpx.ConnectError("certificate verify failed")

    monkeypatch.setattr("app.nextcloud.client.httpx.AsyncClient", FailingAsyncClient)
    client = NextcloudClient(settings)

    with pytest.raises(NextcloudError) as exc_info:
        asyncio.run(client._request("GET", "https://nextcloud.example.com/status.php"))

    assert exc_info.value.status_code == 502
    assert "Unable to connect to Nextcloud" in exc_info.value.message


def test_parse_propfind_skips_requested_root(settings):
    client = NextcloudClient(settings)
    xml = b"""<?xml version="1.0"?>
    <d:multistatus xmlns:d="DAV:">
      <d:response>
        <d:href>/remote.php/dav/files/lijar/Slack/AX%20Project/</d:href>
        <d:propstat><d:prop><d:resourcetype><d:collection /></d:resourcetype></d:prop></d:propstat>
      </d:response>
      <d:response>
        <d:href>/remote.php/dav/files/lijar/Slack/AX%20Project/agent-test.md</d:href>
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


def test_preview_pdf_returns_inline_pdf(settings, monkeypatch):
    async def fake_download(path):
        return DownloadedFile(
            path=path,
            content=b"%PDF-1.7",
            content_type="application/pdf",
            filename="briefing.pdf",
        )

    client = NextcloudClient(settings)
    monkeypatch.setattr(client, "download_file", fake_download)

    preview = asyncio.run(client.preview_file("briefing.pdf"))

    assert preview.viewer_kind == "pdf"
    assert preview.content_type == "application/pdf"
    assert preview.filename == "briefing.pdf"
    assert preview.content == b"%PDF-1.7"


def test_preview_image_returns_browser_safe_image(settings, monkeypatch):
    async def fake_download(path):
        return DownloadedFile(
            path=path,
            content=b"image",
            content_type="image/png",
            filename="diagram.png",
        )

    client = NextcloudClient(settings)
    monkeypatch.setattr(client, "download_file", fake_download)

    preview = asyncio.run(client.preview_file("diagram.png"))

    assert preview.viewer_kind == "image"
    assert preview.content_type == "image/png"


def test_preview_markdown_returns_text(settings, monkeypatch):
    async def fake_download(path):
        return DownloadedFile(
            path=path,
            content="# Notes\n".encode(),
            content_type="text/markdown; charset=utf-8",
            filename="notes.md",
        )

    client = NextcloudClient(settings)
    monkeypatch.setattr(client, "download_file", fake_download)

    preview = asyncio.run(client.preview_file("notes.md"))

    assert preview.viewer_kind == "text"
    assert preview.content_type == "text/markdown; charset=utf-8"
    assert preview.content == b"# Notes\n"


def test_preview_unsupported_file_type_fails(settings, monkeypatch):
    async def fake_download(path):
        return DownloadedFile(
            path=path,
            content=b"archive",
            content_type="application/zip",
            filename="backup.zip",
        )

    client = NextcloudClient(settings)
    monkeypatch.setattr(client, "download_file", fake_download)

    with pytest.raises(NextcloudError) as exc_info:
        asyncio.run(client.preview_file("backup.zip"))

    assert exc_info.value.status_code == 415


def test_preview_docx_requires_libreoffice(settings, monkeypatch):
    async def fake_download(path):
        return DownloadedFile(
            path=path,
            content=b"docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="proposal.docx",
        )

    client = NextcloudClient(settings)
    monkeypatch.setattr(client, "download_file", fake_download)
    monkeypatch.setattr("app.nextcloud.client.shutil.which", lambda command: None)

    with pytest.raises(NextcloudError) as exc_info:
        asyncio.run(client.preview_file("proposal.docx"))

    assert exc_info.value.status_code == 501
    assert "LibreOffice" in exc_info.value.message


def test_preview_pptx_conversion_returns_pdf(settings, monkeypatch):
    async def fake_download(path):
        return DownloadedFile(
            path=path,
            content=b"pptx",
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename="deck.pptx",
        )

    def fake_run(args, **kwargs):
        outdir = args[args.index("--outdir") + 1]
        with open(f"{outdir}/deck.pdf", "wb") as file:
            file.write(b"%PDF-converted")
        return None

    client = NextcloudClient(settings)
    monkeypatch.setattr(client, "download_file", fake_download)
    monkeypatch.setattr("app.nextcloud.client.shutil.which", lambda command: "/usr/bin/soffice")
    monkeypatch.setattr("app.nextcloud.client.subprocess.run", fake_run)

    preview = asyncio.run(client.preview_file("deck.pptx"))

    assert preview.viewer_kind == "pdf"
    assert preview.content_type == "application/pdf"
    assert preview.filename == "deck.pdf"
    assert preview.content == b"%PDF-converted"


def test_preview_xlsx_conversion_returns_pdf(settings, monkeypatch):
    async def fake_download(path):
        return DownloadedFile(
            path=path,
            content=b"xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="budget.xlsx",
        )

    def fake_run(args, **kwargs):
        outdir = args[args.index("--outdir") + 1]
        with open(f"{outdir}/budget.pdf", "wb") as file:
            file.write(b"%PDF-sheet")
        return None

    client = NextcloudClient(settings)
    monkeypatch.setattr(client, "download_file", fake_download)
    monkeypatch.setattr("app.nextcloud.client.shutil.which", lambda command: "/usr/bin/soffice")
    monkeypatch.setattr("app.nextcloud.client.subprocess.run", fake_run)

    preview = asyncio.run(client.preview_file("budget.xlsx"))

    assert preview.viewer_kind == "pdf"
    assert preview.content_type == "application/pdf"
    assert preview.filename == "budget.pdf"
    assert preview.content == b"%PDF-sheet"


def test_empty_path_is_slack_root(settings):
    client = NextcloudClient(settings)
    assert client._absolute_webdav_url("", trailing_slash=True).endswith("/files/lijar/Slack/")
    assert client._absolute_webdav_url("/Reports/notes.md").endswith("/files/lijar/Slack/Reports/notes.md")


@pytest.mark.parametrize("href", [
    "/remote.php/dav/files/lijar/Private/secret.txt",
    "/remote.php/dav/files/lijar/Shared/secret.txt",
    "/remote.php/dav/files/lijar/Slack-other/secret.txt",
    "/remote.php/dav/files/other-user/Slack/secret.txt",
    "/remote.php/dav/files/lijar/Slack/../Private/secret.txt",
    "/remote.php/dav/files/lijar/Slack/%2e%2e/Private/secret.txt",
    "https://other.example/remote.php/dav/files/lijar/Slack/secret.txt",
])
def test_listing_hrefs_outside_slack_are_ignored(settings, href):
    assert NextcloudClient(settings)._path_from_href(href) is None


def test_slack_hrefs_round_trip_unicode_spaces_and_percent_characters(settings):
    client = NextcloudClient(settings)
    path = "보고서/100% # 완료.md"
    assert client._path_from_href(client._absolute_webdav_url(path)) == path


def test_slack_listing_excludes_siblings_and_nested_files(settings):
    client = NextcloudClient(settings)
    hrefs = ["Slack/", "Slack/report.md", "Private/secret.md", "Slack/nested/deep.md"]
    xml = ('<d:multistatus xmlns:d="DAV:">' + ''.join(
        f'<d:response><d:href>/remote.php/dav/files/lijar/{href}</d:href>'
        '<d:propstat><d:prop><d:resourcetype /></d:prop></d:propstat></d:response>'
        for href in hrefs) + '</d:multistatus>').encode()
    items = client._parse_propfind(xml, root_path="")
    assert [item.path for item in items] == ["report.md"]


def test_file_operations_and_copy_destination_stay_in_slack(settings, monkeypatch):
    client = NextcloudClient(settings)
    requests = []
    async def request(method, url, **kwargs):
        requests.append((method, url, kwargs))
        return httpx.Response(201 if method in {"COPY", "MOVE", "MKCOL", "PUT"} else 200,
                              content=b"contents", headers={"content-type": "text/plain"})
    monkeypatch.setattr(client, "_request", request)
    async def operations():
        await client.download_file("report.txt")
        await client.read_text_file("report.txt")
        await client.preview_file("report.txt")
        await client.copy("report.txt", "archive/copy.txt", False)
        await client.move("report.txt", "archive/moved.txt", False)
        await client.delete("old.txt")
    asyncio.run(operations())
    for _, url, kwargs in requests:
        assert "/files/lijar/Slack/" in url
        destination = kwargs.get("headers", {}).get("Destination")
        if destination:
            assert "/files/lijar/Slack/archive/" in destination
