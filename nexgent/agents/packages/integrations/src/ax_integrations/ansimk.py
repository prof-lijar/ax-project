"""Fixed-origin Ansimk admin login and one device signal check; secrets stay local."""

import asyncio
import json
import os
import re
import tempfile
import time
from pathlib import Path

import httpx

BASE_URL = "https://dev-check.ansimk.com"
COOKIE = "device_check_session"


class AnsimkError(RuntimeError):
    """Sanitized authentication, transport or response failure."""


class AnsimkClient:
    def __init__(self, http, *, code_file, session_file, seed_file=None):
        self.http = http
        self.code_file = Path(code_file)
        self.session_file = Path(session_file)
        self.seed_file = Path(seed_file) if seed_file else None

    @classmethod
    def from_env(cls, http):
        private = Path.home() / ".local/share/nexgent"
        return cls(
            http,
            code_file=os.getenv(
                "AX768_ANSIMK_CODE_FILE", str(private / "ansimk-admin-code")
            ),
            session_file=os.getenv(
                "AX768_ANSIMK_SESSION_FILE", str(private / "ansimk-api-session.json")
            ),
            seed_file=os.getenv(
                "AX768_ANSIMK_SESSION_SEED_FILE",
                str(private / "ansimk-admin-session.json"),
            ),
        )

    def _load_session(self):
        for path in (self.session_file, self.seed_file):
            if path is None or not path.is_file():
                continue
            try:
                if path.stat().st_size > 32000:
                    continue
                state = json.loads(path.read_text())
                for cookie in state.get("cookies", []):
                    if (
                        cookie.get("name") == COOKIE
                        and cookie.get("domain", "").lstrip(".")
                        == "dev-check.ansimk.com"
                        and cookie.get("path") == "/"
                        and cookie.get("secure") is True
                        and isinstance(cookie.get("expires"), (int, float))
                        and cookie["expires"] > time.time() + 60
                        and isinstance(cookie.get("value"), str)
                        and cookie["value"]
                    ):
                        self.http.cookies.set(
                            COOKIE,
                            cookie["value"],
                            domain="dev-check.ansimk.com",
                            path="/",
                        )
                        return
            except (OSError, ValueError, TypeError, AttributeError):
                continue

    def _save_session(self):
        cookies = [
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
                "secure": c.secure,
                "expires": c.expires or -1,
            }
            for c in self.http.cookies.jar
            if c.name == COOKIE and c.domain.lstrip(".") == "dev-check.ansimk.com"
        ]
        parent = self.session_file.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=parent, delete=False
            ) as stream:
                temporary = stream.name
                os.chmod(temporary, 0o600)
                json.dump({"cookies": cookies}, stream)
            os.replace(temporary, self.session_file)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    async def _login(self):
        try:
            if self.code_file.stat().st_size > 1000:
                raise ValueError("invalid code file")
            code = (await asyncio.to_thread(self.code_file.read_text)).strip()
            if not code or "\n" in code:
                raise ValueError("invalid code file")
        except (OSError, ValueError):
            raise AnsimkError(
                "설치보고관리 로그인 코드 파일을 확인해 주세요."
            ) from None
        try:
            response = await self.http.post(
                BASE_URL + "/api/admin/login", json={"code": code}
            )
        except httpx.HTTPError:
            raise AnsimkError("설치보고관리 로그인 연결에 실패했습니다.") from None
        if response.status_code != 200 or not any(
            c.name == COOKIE and c.domain.lstrip(".") == "dev-check.ansimk.com"
            for c in self.http.cookies.jar
        ):
            raise AnsimkError(
                "설치보고관리 로그인에 실패했습니다. 관리자 코드와 접근 권한을 확인해 주세요."
            )
        try:
            await asyncio.to_thread(self._save_session)
        except OSError:
            raise AnsimkError(
                "설치보고관리 세션을 안전하게 저장하지 못했습니다."
            ) from None

    async def ping(self, imei):
        if not isinstance(imei, str) or not re.fullmatch(r"[0-9]{15}", imei):
            raise AnsimkError("IMEI는 15자리 숫자여야 합니다.")
        try:
            async with asyncio.timeout(75):
                await asyncio.to_thread(self._load_session)
                # Only an authentication rejection permits one login and resubmission.
                # No retry follows a timeout, Cloudflare block or server error.
                if not any(c.name == COOKIE for c in self.http.cookies.jar):
                    await self._login()
                    logged_in = True
                else:
                    logged_in = False
                response = await self.http.post(
                    BASE_URL + "/api/admin/ping", json={"sn": imei}
                )
                if response.status_code == 401 and not logged_in:
                    self.http.cookies.clear()
                    await self._login()
                    response = await self.http.post(
                        BASE_URL + "/api/admin/ping", json={"sn": imei}
                    )
                if response.status_code != 200:
                    raise AnsimkError(
                        f"설치보고관리 신호 확인 API 오류 (HTTP {response.status_code}). 연결 상태는 확인되지 않았습니다."
                    )
                if len(response.content) > 64000:
                    raise AnsimkError("신호 확인 응답이 허용 크기를 초과했습니다.")
                return normalize_ping(response.json(), imei)
        except (httpx.HTTPError, TimeoutError, ValueError):
            raise AnsimkError(
                "신호 확인 응답을 받지 못했습니다. 연결 상태는 확인되지 않았습니다."
            ) from None


def normalize_ping(data, imei):
    if (
        not isinstance(data, dict)
        or data.get("imei") != imei
        or type(data.get("connected")) is not bool
        or not isinstance(data.get("sn"), str)
        or not re.fullmatch(r"[0-9]{1,32}", data["sn"])
    ):
        raise AnsimkError(
            "신호 확인 응답의 IMEI, S/N 또는 연결 상태를 검증하지 못했습니다."
        )
    if data["connected"] and data.get("fresh") is not True:
        raise AnsimkError("최신 기기 응답 여부를 확인하지 못했습니다.")
    signal = data.get("signal") if isinstance(data.get("signal"), dict) else {}
    elapsed = data.get("elapsed_ms")
    rssi = signal.get("rssi")
    return {
        "imei": imei,
        "sn": data["sn"],
        "connected": data["connected"],
        "fresh": data.get("fresh") is True,
        "elapsed_ms": elapsed
        if type(elapsed) in {int, float} and 0 <= elapsed <= 300000
        else None,
        "signal_label": signal.get("label")[:80]
        if isinstance(signal.get("label"), str)
        else None,
        "rssi": rssi if type(rssi) in {int, float} and -200 <= rssi <= 200 else None,
        "message": data.get("message", "")[:500]
        if isinstance(data.get("message"), str)
        else "",
    }
