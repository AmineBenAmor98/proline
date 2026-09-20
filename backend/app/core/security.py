"""Admin authentication.

Sprint 1 uses a single shared token read from the environment: enough for one
person, nothing to store, nothing to leak beyond the token itself. Sprint 4
replaces this with per-user auth without touching the routers.
"""

import hmac

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings


async def require_admin(
    authorization: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin access is not configured",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, settings.admin_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")
