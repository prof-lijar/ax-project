"""Admin session handling and truthful device signal receipts."""

import json
import time

import httpx
import pytest
from ax_integrations.ansimk import AnsimkClient, AnsimkError, normalize_ping

IMEI = "861212072106726"


def result(connected=True):
    return {
        "imei": IMEI,
        "sn": "00300016",
        "connected": connected,
        "fresh": connected,
        "signal": {"label": "보통", "rssi": 22},
        "elapsed_ms": 1454,
        "message": "response",
        "raw": "private raw",
        "device": {"ward_name": "excluded"},
    }


def seed(path):
    path.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "device_check_session",
                        "value": "cached-secret",
                        "domain": "dev-check.ansimk.com",
                        "path": "/",
                        "secure": True,
                        "expires": time.time() + 10000,
                    }
                ]
            }
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "cached",
        "login",
        "expired",
        "disconnected",
        "forbidden",
        "timeout",
        "bad_login",
        "malformed",
        "mismatch",
    ],
)
async def test_cookie_login_bounded_retry_and_response(tmp_path, mode):
    code = tmp_path / "code"
    code.write_text("login-secret\n")
    cache = tmp_path / "session"
    cached = tmp_path / "seed"
    seed(cached)
    requests = []
    ping_count = 0

    def handle(request):
        nonlocal ping_count
        requests.append(request)
        if request.url.path.endswith("/login"):
            assert json.loads(request.content) == {"code": "login-secret"}
            return httpx.Response(
                403 if mode == "bad_login" else 200,
                json={"ok": True},
                headers={}
                if mode == "bad_login"
                else {
                    "Set-Cookie": "device_check_session=renewed-secret; Max-Age=2592000; Path=/; Secure; HttpOnly"
                },
            )
        assert request.url.path == "/api/admin/ping" and request.method == "POST"
        assert json.loads(request.content) == {"sn": IMEI}
        ping_count += 1
        if mode == "expired" and ping_count == 1:
            return httpx.Response(401, json={})
        if mode == "forbidden":
            return httpx.Response(403, json={"detail": "cached-secret"})
        if mode == "timeout":
            raise httpx.ReadTimeout("cached-secret", request=request)
        body = result(mode != "disconnected")
        if mode == "malformed":
            body["connected"] = "false"
        if mode == "mismatch":
            body["imei"] = "861212072106727"
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = AnsimkClient(
            http,
            code_file=code,
            session_file=cache,
            seed_file=None if mode in {"login", "bad_login"} else cached,
        )
        if mode in {"forbidden", "timeout", "bad_login", "malformed", "mismatch"}:
            with pytest.raises(AnsimkError) as error:
                await client.ping(IMEI)
            assert "secret" not in str(error.value)
        else:
            output = await client.ping(IMEI)
            assert output["sn"] == "00300016" and output["connected"] == (
                mode != "disconnected"
            )
            assert "raw" not in output and "device" not in output
    assert ping_count == (0 if mode == "bad_login" else 2 if mode == "expired" else 1)
    if mode in {"login", "expired"}:
        assert cache.stat().st_mode & 0o777 == 0o600
        assert json.loads(cache.read_text())["cookies"][0]["value"] == "renewed-secret"
    elif mode == "cached":
        assert all(
            r.headers.get("cookie") == "device_check_session=cached-secret"
            for r in requests
        )
        assert len(requests) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"imei": "different"},
        {"connected": 0},
        {"sn": 123},
        {"sn": ""},
        {"fresh": False},
        {"connected": None},
    ],
)
def test_unverified_or_wrong_device_is_not_connected(change):
    with pytest.raises(AnsimkError):
        normalize_ping({**result(), **change}, IMEI)


@pytest.mark.asyncio
async def test_invalid_imei_or_missing_code_never_pings(tmp_path):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = AnsimkClient(
            http, code_file=tmp_path / "missing", session_file=tmp_path / "cache"
        )
        for imei in ["123", "1e14", IMEI]:
            with pytest.raises(AnsimkError):
                await client.ping(imei)
    assert not calls
