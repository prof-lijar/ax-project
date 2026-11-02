"""Google user OAuth for Linux CLI agents; tokens never enter graph state."""

import asyncio
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from ax_integrations.google_sheets import SCOPE, SheetsError


def save_credentials(path: Path, credentials) -> None:
    """Atomically replace a private token file; caller owns the refresh lock."""
    if not credentials.refresh_token or not credentials.has_scopes([SCOPE]):
        raise ValueError("Google must grant offline access and the Sheets scope")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".oauth-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(credentials.to_json())
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def token_lock(path: Path):
    # Shared across short-lived graph nodes and local worker processes.
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


class OAuthToken:
    def __init__(self, filename: str):
        self.path = Path(filename)

    async def __call__(self) -> str:
        try:
            return await asyncio.to_thread(self._get)
        except (GoogleAuthError, OSError, ValueError, KeyError):
            raise SheetsError(
                "Google OAuth unavailable or expired; run python -m apps.ax768.oauth_login again."
            ) from None

    def _get(self):
        with token_lock(self.path):
            if self.path.is_symlink():
                raise ValueError("token file must not be a symlink")
            credentials = Credentials.from_authorized_user_file(str(self.path))
            if not credentials.has_scopes([SCOPE]):
                raise ValueError("missing Sheets permission")
            if not credentials.valid:
                credentials.refresh(Request())
                save_credentials(self.path, credentials)
            return credentials.token


def login(client_file: str, token_file: str, *, port: int = 8767):
    """Loopback authorization with PKCE/state handled by Google's library."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    config = json.loads(Path(client_file).read_text())
    installed = config.get("installed", {})
    if (
        installed.get("auth_uri") != "https://accounts.google.com/o/oauth2/auth"
        or installed.get("token_uri") != "https://oauth2.googleapis.com/token"
    ):
        raise ValueError("use a downloaded Google Desktop app OAuth client JSON")
    if Path(client_file).resolve() == Path(token_file).resolve():
        raise ValueError("client and token files must be different")
    flow = InstalledAppFlow.from_client_config(
        config,
        scopes=[SCOPE],
        autogenerate_code_verifier=True,
    )
    credentials = flow.run_local_server(
        host="127.0.0.1",
        bind_addr="127.0.0.1",
        port=port,
        open_browser=False,
        timeout_seconds=300,
        prompt="consent",
        authorization_prompt_message="Open this URL in your browser: {url}",
        success_message="AX768 authorization received. You can close this tab.",
    )
    with token_lock(Path(token_file)):
        save_credentials(Path(token_file), credentials)
