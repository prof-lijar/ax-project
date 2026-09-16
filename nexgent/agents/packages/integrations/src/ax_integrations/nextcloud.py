"""Bounded Nextcloud WebDAV operations within one configured account."""

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

import httpx

from .file_http import FileIntegrationError, bounded_response


def path_component(value: str) -> str:
    value = re.sub(r'[\\/\x00-\x1f\x7f<>:"|?*]', "_", value).strip(" .")
    # Cap UTF-8 bytes for filesystem-backed Nextcloud storage.
    return value.encode()[:160].decode("utf-8", errors="ignore") or "unnamed"


@dataclass(frozen=True)
class CloudFile:
    name: str
    url: str


class Nextcloud:
    def __init__(
        self, base_url: str, username: str, password: str, http: httpx.AsyncClient
    ):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or any(part in {".", ".."} for part in unquote(parsed.path).split("/"))
        ):
            raise ValueError("Nextcloud requires an HTTPS base URL without credentials")
        if not username or username in {".", ".."} or "/" in username:
            raise ValueError("invalid Nextcloud username")
        self.base = base_url.rstrip("/")
        self.dav = f"{self.base}/remote.php/dav/files/{quote(username, safe='')}"
        self.auth = httpx.BasicAuth(username, password)
        self.http = http

    def url(self, path: str) -> str:
        if not path or any(p in {"", ".", ".."} for p in path.split("/")):
            raise ValueError("invalid relative cloud path")
        return self.dav + "/" + quote(path, safe="/")

    async def request(self, method: str, path: str, *, limit=4 * 1024 * 1024, **kwargs):
        async with self.http.stream(
            method,
            self.url(path),
            auth=self.auth,
            follow_redirects=False,
            **kwargs,
        ) as response:
            body = await bounded_response(response, limit)
            return response.status_code, body

    async def mkdirs(self, path: str) -> None:
        parts = path.split("/")
        for index in range(1, len(parts) + 1):
            current = "/".join(parts[:index])
            code, _ = await self.request("MKCOL", current)
            if code == 405:
                code, body = await self.request(
                    "PROPFIND",
                    current,
                    headers={"Depth": "0"},
                )
                if code != 207 or (b"<!DOCTYPE" in body.upper() or b"\x00" in body):
                    raise FileIntegrationError("nextcloud_folder_conflict")
                if ET.fromstring(body).find(".//{DAV:}collection") is None:
                    raise FileIntegrationError("nextcloud_folder_conflict")
            elif code != 201:
                raise FileIntegrationError("nextcloud_mkdir_failed")

    async def put_once(self, path: str, data: bytes) -> None:
        code, _ = await self.request(
            "PUT",
            path,
            content=data,
            headers={"If-None-Match": "*"},
        )
        if code == 412:
            # Replays must match existing bytes; never accept or overwrite a collision.
            code, existing = await self.request("GET", path, limit=max(1, len(data)))
            if (
                code != 200
                or hashlib.sha256(existing).digest() != hashlib.sha256(data).digest()
            ):
                raise FileIntegrationError("nextcloud_file_conflict")
        elif code not in {201, 204}:
            raise FileIntegrationError("nextcloud_upload_failed")

    async def list_files(self, folder: str) -> list[CloudFile]:
        code, body = await self.request(
            "PROPFIND",
            folder,
            headers={"Depth": "1", "Content-Type": "application/xml"},
            content=b'<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
            b"<d:prop><d:resourcetype/><oc:fileid/></d:prop></d:propfind>",
        )
        if code == 404:
            return []
        if (
            code != 207
            or (b"<!DOCTYPE" in body.upper() or b"\x00" in body)
            or b"<!ENTITY" in body.upper()
        ):
            raise FileIntegrationError("nextcloud_listing_failed")
        expected = unquote(urlsplit(self.url(folder)).path).rstrip("/") + "/"
        files = []
        for response in ET.fromstring(body).findall("{DAV:}response"):
            href = response.findtext("{DAV:}href", "")
            parsed = urlsplit(href)
            if parsed.netloc and parsed.netloc != urlsplit(self.base).netloc:
                continue
            path = unquote(parsed.path)
            if not path.startswith(expected):
                continue
            name = path[len(expected) :]
            if not name or "/" in name or name in {".", ".."}:
                continue
            for propstat in response.findall("{DAV:}propstat"):
                if " 200 " not in propstat.findtext("{DAV:}status", ""):
                    continue
                prop = propstat.find("{DAV:}prop")
                if prop is None or prop.find(".//{DAV:}collection") is not None:
                    continue
                file_id = prop.findtext("{http://owncloud.org/ns}fileid", "")
                if file_id.isdigit():
                    files.append(CloudFile(name, f"{self.base}/index.php/f/{file_id}"))
        return files
