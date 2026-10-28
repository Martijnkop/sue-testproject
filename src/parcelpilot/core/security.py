from __future__ import annotations

from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from parcelpilot.settings import settings

bearer_scheme = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:  # pragma: no cover - defensive guard for invalid tokens
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "Token is invalid or expired"},
        ) from exc
    return payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "missing_credentials", "message": "Authentication credentials were not provided"},
        )

    payload = _decode_token(credentials.credentials)
    return {
        "token": credentials.credentials,
        "user_id": payload.get("user_id", 0),
        "tenant_id": payload.get("tenant_id", 0),
        "tenant_slug": payload.get("tenant_slug", "acme"),
        "role": payload.get("role", "viewer"),
        "email": payload.get("email", ""),
        "full_name": payload.get("full_name", ""),
        "is_active": True,
        "last_login_at": payload.get("last_login_at"),
    }


def get_tenant(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"tenant_id": user.get("tenant_id"), "tenant_slug": user.get("tenant_slug")}


def require_roles(*roles: str):
    async def dependency(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if not roles:
            return user
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "forbidden", "message": "Role not allowed for this resource"},
            )
        return user

    return dependency
