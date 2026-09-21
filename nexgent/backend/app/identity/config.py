from dataclasses import dataclass, field
from hashlib import sha256
import os
from urllib.parse import urlsplit


@dataclass(frozen=True)
class IdentitySettings:
    database_url: str = field(repr=False)
    public_url: str
    signing_key: str = field(repr=False)
    secure_cookies: bool = True
    login_seconds: int = 28800

    @property
    def cookie_name(self) -> str:
        # Cookies do not have port isolation; dev/prod on one host need distinct names.
        suffix = sha256(self.public_url.encode()).hexdigest()[:8]
        prefix = "__Host-nexgent_login" if self.secure_cookies else "nexgent_local_login"
        return f"{prefix}_{suffix}"


def load_identity_settings() -> IdentitySettings:
    def required(name: str) -> str:
        value = os.getenv(name, "").strip()
        if not value:
            raise ValueError(f"{name} is required")
        return value

    public = required("NEXGENT_PUBLIC_URL").rstrip("/")
    parts = urlsplit(public)
    if (parts.username or parts.password or parts.query or parts.fragment or parts.path
            or not parts.hostname or parts.scheme not in {"http", "https"}):
        raise ValueError("NEXGENT_PUBLIC_URL must be a valid origin")
    if parts.scheme != "https" and os.getenv("NEXGENT_ALLOW_INSECURE_HTTP") != "true":
        raise ValueError("HTTPS is required; HTTP development must be explicitly enabled")
    database = required("NEXGENT_DATABASE_URL")
    if not database.startswith("postgresql+psycopg://"):
        raise ValueError("Nexgent requires a postgresql+psycopg database URL")
    key = required("NEXGENT_AUTH_SIGNING_KEY")
    if len(key.encode()) < 32:
        raise ValueError("NEXGENT_AUTH_SIGNING_KEY must contain at least 32 random bytes")
    lifetime = int(os.getenv("NEXGENT_LOGIN_SECONDS", "28800"))
    if not 300 <= lifetime <= 86400:
        raise ValueError("NEXGENT_LOGIN_SECONDS must be between 300 and 86400")
    return IdentitySettings(database, public, key, parts.scheme == "https", lifetime)
