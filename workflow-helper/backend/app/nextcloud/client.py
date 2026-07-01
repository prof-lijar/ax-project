from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote, unquote
import posixpath
import xml.etree.ElementTree as ET

import httpx

from app.core.settings import Settings
from app.nextcloud.schemas import FileItem


DAV_NS = "{DAV:}"
NC_OCS_META_STATUS_OK = {"ok", "100", "200"}


class NextcloudError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class DownloadedFile:
    path: str
    content: bytes
    content_type: str | None
    filename: str


class NextcloudClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.nextcloud_url
        self._user = settings.nextcloud_user
        self._auth = (settings.nextcloud_user, settings.nextcloud_password)
        self._verify = settings.nextcloud_verify_ssl
        self._timeout = settings.nextcloud_timeout_seconds

    async def list_files(self, path: str = "", depth: int = 1) -> list[FileItem]:
        if depth not in {0, 1}:
            raise NextcloudError("Depth must be 0 or 1.", status_code=400)

        response = await self._request(
            "PROPFIND",
            self._webdav_url(path, trailing_slash=True),
            headers={"Depth": str(depth)},
        )
        self._raise_for_status(response)
        return self._parse_propfind(response.content, root_path=self._clean_path(path))

    async def download_file(self, path: str) -> DownloadedFile:
        clean_path = self._clean_path(path)
        response = await self._request("GET", self._webdav_url(clean_path))
        self._raise_for_status(response)
        return DownloadedFile(
            path=clean_path,
            content=response.content,
            content_type=response.headers.get("content-type"),
            filename=PurePosixPath(clean_path).name or "download",
        )

    async def read_text_file(self, path: str) -> tuple[str, str | None]:
        downloaded = await self.download_file(path)
        content_type = downloaded.content_type
        charset = "utf-8"
        if content_type and "charset=" in content_type:
            charset = content_type.rsplit("charset=", 1)[1].split(";", 1)[0].strip()
        return downloaded.content.decode(charset), content_type

    async def write_text_file(
        self,
        path: str,
        content: str,
        content_type: str,
    ) -> int:
        response = await self._request(
            "PUT",
            self._webdav_url(path),
            content=content.encode("utf-8"),
            headers={"Content-Type": content_type},
        )
        self._raise_for_status(response, expected={200, 201, 204})
        return response.status_code

    async def upload_file(
        self,
        path: str,
        content: bytes,
        content_type: str | None = None,
    ) -> int:
        headers = {"Content-Type": content_type} if content_type else None
        response = await self._request(
            "PUT",
            self._webdav_url(path),
            content=content,
            headers=headers,
        )
        self._raise_for_status(response, expected={200, 201, 204})
        return response.status_code

    async def create_folder(self, path: str) -> int:
        response = await self._request("MKCOL", self._webdav_url(path, trailing_slash=True))
        self._raise_for_status(response, expected={201, 405})
        return response.status_code

    async def delete(self, path: str) -> int:
        response = await self._request("DELETE", self._webdav_url(path))
        self._raise_for_status(response, expected={200, 202, 204})
        return response.status_code

    async def copy(self, source_path: str, destination_path: str, overwrite: bool) -> int:
        response = await self._request(
            "COPY",
            self._webdav_url(source_path),
            headers={
                "Destination": self._absolute_webdav_url(destination_path),
                "Overwrite": "T" if overwrite else "F",
            },
        )
        self._raise_for_status(response, expected={201, 204})
        return response.status_code

    async def move(self, source_path: str, destination_path: str, overwrite: bool) -> int:
        response = await self._request(
            "MOVE",
            self._webdav_url(source_path),
            headers={
                "Destination": self._absolute_webdav_url(destination_path),
                "Overwrite": "T" if overwrite else "F",
            },
        )
        self._raise_for_status(response, expected={201, 204})
        return response.status_code

    async def capabilities(self) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"{self._base_url}/ocs/v1.php/cloud/capabilities",
            headers={"OCS-APIRequest": "true", "Accept": "application/json"},
        )
        self._raise_for_status(response)
        data = response.json()
        status = str(data.get("ocs", {}).get("meta", {}).get("statuscode", ""))
        message = data.get("ocs", {}).get("meta", {}).get("message", "Nextcloud OCS error")
        if status and status not in NC_OCS_META_STATUS_OK:
            raise NextcloudError(message, status_code=502)
        return data.get("ocs", {}).get("data", data)

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(
            auth=self._auth,
            verify=self._verify,
            timeout=self._timeout,
            follow_redirects=True,
        ) as client:
            return await client.request(method, url, **kwargs)

    def _webdav_url(self, path: str, trailing_slash: bool = False) -> str:
        return self._absolute_webdav_url(path, trailing_slash=trailing_slash)

    def _absolute_webdav_url(self, path: str, trailing_slash: bool = False) -> str:
        clean_path = self._clean_path(path)
        encoded_parts = [quote(part, safe="") for part in clean_path.split("/") if part]
        encoded_path = "/".join(encoded_parts)
        url = f"{self._base_url}/remote.php/dav/files/{quote(self._user, safe='')}/"
        if encoded_path:
            url = f"{url}{encoded_path}"
        if trailing_slash and not url.endswith("/"):
            url = f"{url}/"
        return url

    @staticmethod
    def _clean_path(path: str) -> str:
        if any(part == ".." for part in path.split("/")):
            raise NextcloudError("Path traversal is not allowed.", status_code=400)
        normalized = posixpath.normpath(f"/{path.strip('/')}")
        if normalized == "/":
            return ""
        return normalized.strip("/")

    @staticmethod
    def _raise_for_status(
        response: httpx.Response,
        expected: set[int] | None = None,
    ) -> None:
        expected_codes = expected or set(range(200, 300))
        if response.status_code in expected_codes:
            return
        detail = response.text[:500] if response.text else response.reason_phrase
        raise NextcloudError(detail, status_code=response.status_code)

    def _parse_propfind(self, xml_content: bytes, root_path: str) -> list[FileItem]:
        root = ET.fromstring(xml_content)
        items: list[FileItem] = []
        root_clean = root_path.strip("/")

        for response in root.findall(f"{DAV_NS}response"):
            href = response.findtext(f"{DAV_NS}href") or ""
            item_path = self._path_from_href(href)
            if item_path.rstrip("/") == root_clean.rstrip("/"):
                continue

            prop = response.find(f"{DAV_NS}propstat/{DAV_NS}prop")
            if prop is None:
                continue

            resource_type = prop.find(f"{DAV_NS}resourcetype")
            is_directory = (
                resource_type is not None
                and resource_type.find(f"{DAV_NS}collection") is not None
            )
            name = PurePosixPath(item_path.rstrip("/")).name
            size_text = prop.findtext(f"{DAV_NS}getcontentlength")
            items.append(
                FileItem(
                    path=item_path.rstrip("/"),
                    name=name,
                    is_directory=is_directory,
                    content_type=prop.findtext(f"{DAV_NS}getcontenttype"),
                    size=int(size_text) if size_text and size_text.isdigit() else None,
                    etag=prop.findtext(f"{DAV_NS}getetag"),
                    last_modified=prop.findtext(f"{DAV_NS}getlastmodified"),
                )
            )
        return items

    def _path_from_href(self, href: str) -> str:
        marker = f"/remote.php/dav/files/{quote(self._user, safe='')}/"
        if marker not in href:
            return unquote(href.strip("/"))
        path = href.split(marker, 1)[1]
        return unquote(httpx.URL(f"http://local/{path}").path.lstrip("/"))
