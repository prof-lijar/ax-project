"""Fixed-origin member-admin API; credentials and tokens never enter receipts."""

import asyncio
import json
import os
from pathlib import Path

import httpx

BASE_URL = "https://api.ansimk.com"


class MembersError(RuntimeError):
    pass


class MembersRejected(MembersError):
    """An explicit client-error response rejected the write."""


class AnsimkMembersClient:
    def __init__(self, http, credential_file):
        self.http = http
        self.credential_file = Path(credential_file)
        self._token = None

    @classmethod
    def from_env(cls, http):
        return cls(
            http,
            os.getenv(
                "AX768_MEMBERS_CREDENTIALS_FILE",
                str(
                    Path.home() / ".local/share/nexgent/ansimk-members-credentials.json"
                ),
            ),
        )

    async def login(self):
        def read():
            try:
                if (
                    self.credential_file.stat().st_mode & 0o077
                    or self.credential_file.stat().st_size > 8000
                ):
                    raise ValueError()
                value = json.loads(self.credential_file.read_text())
                if not isinstance(value, dict) or set(value) != {
                    "username",
                    "password",
                }:
                    raise ValueError()
                if any(
                    not isinstance(x, str) or not x or len(x) > 1000
                    for x in value.values()
                ):
                    raise ValueError()
                return value
            except (OSError, ValueError):
                raise MembersError(
                    "가입자 관리 로그인 파일과 권한(600)을 확인해 주세요."
                ) from None

        credentials = await asyncio.to_thread(read)
        value = await self._request("POST", "/token/", json=credentials)
        token = value.get("access") if isinstance(value, dict) else None
        if not isinstance(token, str) or not token or len(token) > 16000:
            raise MembersError("가입자 관리 로그인 응답을 확인하지 못했습니다.")
        self._token = token

    async def _request(self, method, path, **kwargs):
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        try:
            response = await self.http.request(
                method, BASE_URL + path, headers=headers, **kwargs
            )
        except httpx.HTTPError:
            raise MembersError("가입자 관리 연결 결과를 확인하지 못했습니다.") from None
        if 400 <= response.status_code < 500:
            raise MembersRejected(
                f"가입자 관리 요청이 거부되었습니다 (HTTP {response.status_code})."
            )
        if response.status_code != 200 or len(response.content) > 1_000_000:
            raise MembersError("가입자 관리 응답을 확인하지 못했습니다.")
        try:
            return response.json()
        except ValueError:
            raise MembersError("가입자 관리 응답 형식이 올바르지 않습니다.") from None

    async def search(self, name):
        rows, seen, expected = [], set(), None
        for page in range(1, 11):
            value = await self._request(
                "GET",
                "/api/admin/wards/",
                params={"search": name, "page": page, "pageSize": 50},
            )
            if (
                not isinstance(value, dict)
                or type(value.get("totalItemCount")) is not int
                or not isinstance(value.get("data"), list)
            ):
                raise MembersError("가입자 검색 결과 형식이 올바르지 않습니다.")
            total, batch = value["totalItemCount"], value["data"]
            if (
                not 0 <= total <= 500
                or (expected is not None and expected != total)
                or len(batch) > 50
            ):
                raise MembersError(
                    "검색 결과가 너무 많거나 변경되었습니다. 이름과 주소를 확인해 주세요."
                )
            expected = total
            for row in batch:
                if (
                    not isinstance(row, dict)
                    or type(row.get("id")) is not int
                    or row["id"] <= 0
                    or row["id"] in seen
                ):
                    raise MembersError(
                        "가입자 검색 결과가 변경되었습니다. 다시 검색해 주세요."
                    )
                seen.add(row["id"])
                rows.append(row)
            if len(rows) == total:
                return rows
            if not batch or len(rows) > total:
                break
        raise MembersError("전체 가입자 검색 결과를 확인하지 못해 저장하지 않았습니다.")

    async def detail(self, member_id):
        value = await self._request("GET", f"/api/admin/wards/{member_id}/")
        if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
            raise MembersError("가입자 상세 정보 형식이 올바르지 않습니다.")
        row = value["data"]
        if type(row.get("id")) is not int or row["id"] != member_id:
            raise MembersError("가입자 식별 정보가 일치하지 않아 중단했습니다.")
        return row

    async def write_notes(self, member_id, notes):
        # No automatic retries: a timeout can follow an already committed write.
        await self._request(
            "PUT",
            f"/api/admin/wards/{member_id}/update/",
            json={"general_notes": notes},
        )
