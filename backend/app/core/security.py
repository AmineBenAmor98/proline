"""Admin authentication.

Username and password live in the environment (defaults are fine for local dev).
A successful login returns a short-lived token signed with SECRET_KEY: no session
store, no database table, and the password is never sent again after login.

This is deliberately small. When a second person needs access, replace it with
per-user accounts; the routers do not change.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings

TOKEN_TTL_SECONDS = 12 * 60 * 60


def _sign(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _same(left: str, right: str) -> bool:
    """Constant-time comparison that survives an accent.

    `hmac.compare_digest` raises TypeError on str arguments containing anything
    outside ASCII -- so an admin password with an é in it made every sign-in a
    500, including the correct one, and a header byte above 0x7f (Starlette
    decodes headers as latin-1) made every admin endpoint a 500 for anyone who
    sent one. Comparing the UTF-8 bytes has neither problem and is the same
    comparison.
    """
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def create_token(username: str, settings: Settings) -> str:
    payload = json.dumps({"u": username, "exp": int(time.time()) + TOKEN_TTL_SECONDS}).encode()
    body = _b64(payload)
    return f"{body}.{_sign(payload, settings.secret_key)}"


def verify_token(token: str, settings: Settings) -> str | None:
    try:
        body, signature = token.split(".", 1)
        payload = _unb64(body)
    except (ValueError, TypeError):
        return None
    if not _same(signature, _sign(payload, settings.secret_key)):
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data.get("u")


def check_credentials(username: str, password: str, settings: Settings) -> bool:
    """Constant-time on both fields, so timing says nothing about either."""
    user_ok = _same(username.strip(), settings.admin_username)
    password_ok = _same(password, settings.admin_password)
    return user_ok and password_ok


async def require_admin(
    authorization: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="sign in required")
    username = verify_token(token, settings)
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")
    return username
