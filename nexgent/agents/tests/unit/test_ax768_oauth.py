"""Offline OAuth lifecycle checks; no Google account or real tokens required."""

import json
import stat
from datetime import UTC, datetime, timedelta

import pytest
from ax_integrations.google_oauth import OAuthToken, login, save_credentials
from ax_integrations.google_sheets import SCOPE, SheetsError
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


def credentials(*, expired=False, scopes=None, refresh_token="test-refresh"):
    return Credentials(
        token="test-token",
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test-client",
        client_secret="test-secret",
        scopes=scopes or [SCOPE],
        expiry=datetime.now(UTC).replace(tzinfo=None)
        + timedelta(hours=-1 if expired else 1),
    )


@pytest.mark.asyncio
async def test_private_saved_token_can_be_reused_without_refresh(tmp_path, monkeypatch):
    path = tmp_path / "private" / "token.json"
    save_credentials(path, credentials())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def unexpected(*args):
        pytest.fail("valid credentials must not refresh")

    monkeypatch.setattr(Credentials, "refresh", unexpected)
    assert await OAuthToken(str(path))() == "test-token"


@pytest.mark.asyncio
async def test_expired_token_refresh_is_persisted(tmp_path, monkeypatch):
    path = tmp_path / "token.json"
    save_credentials(path, credentials(expired=True))

    def refresh(self, request):
        self.token = "refreshed-token"
        self.expiry = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)

    monkeypatch.setattr(Credentials, "refresh", refresh)
    assert await OAuthToken(str(path))() == "refreshed-token"
    assert json.loads(path.read_text())["token"] == "refreshed-token"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.asyncio
async def test_revocation_is_actionable_and_does_not_leak_provider_data(
    tmp_path, monkeypatch
):
    path = tmp_path / "token.json"
    save_credentials(path, credentials(expired=True))

    def refresh(*args):
        raise RefreshError("sensitive refresh-token details")

    monkeypatch.setattr(Credentials, "refresh", refresh)
    with pytest.raises(SheetsError, match="oauth_login") as error:
        await OAuthToken(str(path))()
    assert "sensitive" not in str(error.value)


def test_does_not_overwrite_existing_token_without_offline_permission(tmp_path):
    path = tmp_path / "token.json"
    save_credentials(path, credentials())
    before = path.read_bytes()
    with pytest.raises(ValueError, match="offline"):
        save_credentials(path, credentials(refresh_token=None))
    assert path.read_bytes() == before


@pytest.mark.asyncio
async def test_readonly_scope_is_rejected(tmp_path):
    path = tmp_path / "token.json"
    path.write_text(credentials(scopes=[SCOPE + ".readonly"]).to_json())
    with pytest.raises(SheetsError, match="oauth_login"):
        await OAuthToken(str(path))()


def test_login_uses_loopback_pkce_and_private_token_storage(tmp_path, monkeypatch):
    client = tmp_path / "client.json"
    token = tmp_path / "token.json"
    client.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "test-client",
                    "client_secret": "test-secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
        )
    )

    def local_server(self, **kwargs):
        assert self.autogenerate_code_verifier
        assert kwargs["host"] == kwargs["bind_addr"] == "127.0.0.1"
        assert kwargs["open_browser"] is False
        assert kwargs["timeout_seconds"] == 300
        assert kwargs["prompt"] == "consent"
        return credentials()

    monkeypatch.setattr(InstalledAppFlow, "run_local_server", local_server)
    login(str(client), str(token))
    assert stat.S_IMODE(token.stat().st_mode) == 0o600
    with pytest.raises(ValueError, match="different"):
        login(str(client), str(client))


def test_service_account_key_is_not_accepted_as_oauth_client(tmp_path):
    client = tmp_path / "client.json"
    client.write_text('{"type":"service_account"}')
    with pytest.raises(ValueError, match="Desktop"):
        login(str(client), str(tmp_path / "token.json"))
