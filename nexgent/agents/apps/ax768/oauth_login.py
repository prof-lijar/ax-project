"""One-time Google sign-in for AX768, through an SSH-forwarded loopback port."""

import argparse
import os
from pathlib import Path

from ax_integrations.google_oauth import login
from dotenv import load_dotenv
from google.auth.exceptions import GoogleAuthError
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    parser = argparse.ArgumentParser(
        description="Authorize AX768 with your Google account"
    )
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    client = os.getenv("AX768_GOOGLE_OAUTH_CLIENT_FILE")
    token = os.getenv("AX768_GOOGLE_OAUTH_TOKEN_FILE")
    if not client or not token:
        parser.error(
            "set AX768_GOOGLE_OAUTH_CLIENT_FILE and AX768_GOOGLE_OAUTH_TOKEN_FILE in agents/.env"
        )
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    print(
        f"Forward laptop port {args.port} to server 127.0.0.1:{args.port} with SSH before opening the URL.",
        flush=True,
    )
    try:
        login(client, token, port=args.port)
    except (
        GoogleAuthError,
        OAuth2Error,
        RequestException,
        OSError,
        ValueError,
        AttributeError,
    ):
        # Google's library can raise AttributeError when no callback arrives before timeout.
        raise SystemExit(
            "OAuth sign-in failed or timed out. Check the Desktop client, consent/test users and SSH tunnel, then retry."
        ) from None
    print(
        "Google OAuth credentials saved privately. AX768 can now use your account's Sheets permissions."
    )


if __name__ == "__main__":
    main()
