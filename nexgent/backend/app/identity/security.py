from dataclasses import dataclass
from hashlib import sha256
import secrets
import time

import jwt
from pwdlib import PasswordHash

passwords = PasswordHash.recommended()
_dummy_hash = passwords.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    if not 4 <= len(password) <= 12:
        raise ValueError("Passwords must contain 4 to 12 characters")
    return passwords.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    valid = passwords.verify(password, password_hash or _dummy_hash)
    return bool(password_hash) and valid


def csrf_token(token: str) -> str:
    return sha256(("nexgent-csrf:" + token).encode()).hexdigest()


@dataclass(frozen=True)
class LoginIdentity:
    user_id: str
    version: int


def issue_token(settings, user_id: str, version: int) -> str:
    stamp = int(time.time())
    return jwt.encode({
        "sub": user_id, "ver": version, "iat": stamp,
        "exp": stamp + settings.login_seconds, "jti": secrets.token_urlsafe(24),
        "iss": "nexgent", "aud": "nexgent-web",
    }, settings.signing_key, algorithm="HS256")


def read_token(settings, token: str | None) -> LoginIdentity | None:
    if not token or len(token) > 4096:
        return None
    try:
        claims = jwt.decode(token, settings.signing_key, algorithms=["HS256"],
                            issuer="nexgent", audience="nexgent-web",
                            options={"require": ["sub", "ver", "iat", "exp", "jti", "iss", "aud"]})
        if type(claims["ver"]) is not int or claims["ver"] < 0:
            return None
        return LoginIdentity(claims["sub"], claims["ver"])
    except jwt.InvalidTokenError:
        return None
