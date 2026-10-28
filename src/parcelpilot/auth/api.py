from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from parcelpilot.auth.passwords import check_password_async, hash_password
from parcelpilot.core.security import get_current_user, require_roles
from parcelpilot.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])

_ALLOWED_ROLES = {"admin", "ops", "analyst", "viewer"}
_DEFAULT_USERS: dict[str, dict[str, Any]] = {
    "admin@acme.example": {
        "id": 1,
        "tenant_id": 1,
        "tenant_slug": "acme",
        "email": "admin@acme.example",
        "full_name": "Acme Admin",
        "role": "admin",
        "password_hash": hash_password("Password123!"),
        "is_active": True,
        "last_login_at": None,
    },
    "ops@acme.example": {
        "id": 2,
        "tenant_id": 1,
        "tenant_slug": "acme",
        "email": "ops@acme.example",
        "full_name": "Acme Ops",
        "role": "ops",
        "password_hash": hash_password("Password123!"),
        "is_active": True,
        "last_login_at": None,
    },
    "analyst@acme.example": {
        "id": 3,
        "tenant_id": 1,
        "tenant_slug": "acme",
        "email": "analyst@acme.example",
        "full_name": "Acme Analyst",
        "role": "analyst",
        "password_hash": hash_password("Password123!"),
        "is_active": True,
        "last_login_at": None,
    },
    "viewer@acme.example": {
        "id": 4,
        "tenant_id": 1,
        "tenant_slug": "acme",
        "email": "viewer@acme.example",
        "full_name": "Acme Viewer",
        "role": "viewer",
        "password_hash": hash_password("Password123!"),
        "is_active": True,
        "last_login_at": None,
    },
}
_REFRESH_TOKENS: dict[str, dict[str, Any]] = {}


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    refresh_token: str = Field(..., min_length=10)


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str
    full_name: str
    password: str = Field(..., min_length=8)
    role: str = "viewer"


def _issue_token(user: dict[str, Any], *, token_type: str, tenant_slug: str) -> str:
    issued_at = dt.datetime.now(dt.timezone.utc)
    payload = {
        "user_id": user["id"],
        "tenant_id": user["tenant_id"],
        "tenant_slug": tenant_slug,
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "type": token_type,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + dt.timedelta(minutes=15)).timestamp()),
    }
    if token_type == "refresh":
        payload["exp"] = int((issued_at + dt.timedelta(days=7)).timestamp())
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _token_response(user: dict[str, Any], *, tenant_slug: str) -> dict[str, Any]:
    access_token = _issue_token(user, token_type="access", tenant_slug=tenant_slug)
    refresh_token = f"rt_{uuid.uuid4().hex}"
    _REFRESH_TOKENS[refresh_token] = {
        "user_id": user["id"],
        "tenant_id": user["tenant_id"],
        "tenant_slug": tenant_slug,
        "email": user["email"],
        "role": user["role"],
        "issued_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 900,
        "user": {
            "id": user["id"],
            "tenant_id": user["tenant_id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            "is_active": user["is_active"],
            "last_login_at": user["last_login_at"],
        },
    }


@router.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    tenant_slug: str = Form(...),
) -> dict[str, Any]:
    email = username.lower()
    user = _DEFAULT_USERS.get(email)
    if user is None or user["tenant_slug"] != tenant_slug.lower():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "Invalid username or password"},
        )

    password_ok = await check_password_async(password, user["password_hash"])
    if not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "Invalid username or password"},
        )

    user["last_login_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return _token_response(user, tenant_slug=tenant_slug.lower())


@router.post("/refresh")
def refresh(payload: RefreshTokenRequest) -> dict[str, Any]:
    session = _REFRESH_TOKENS.get(payload.refresh_token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_refresh_token", "message": "Refresh token is invalid or expired"},
        )

    user = _DEFAULT_USERS.get(session["email"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_refresh_token", "message": "Refresh token is invalid or expired"},
        )

    del _REFRESH_TOKENS[payload.refresh_token]
    return _token_response(user, tenant_slug=session["tenant_slug"])


@router.post("/logout")
def logout(payload: RefreshTokenRequest) -> Response:
    _REFRESH_TOKENS.pop(payload.refresh_token, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me")
def current_user(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "id": user["user_id"],
        "tenant_id": user["tenant_id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "is_active": user["is_active"],
        "last_login_at": user["last_login_at"],
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    user: dict[str, Any] = Depends(require_roles("admin")),
) -> dict[str, Any]:
    email = payload.email.lower()
    if email in _DEFAULT_USERS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "email_already_exists", "message": "User with this email already exists"},
        )

    role = payload.role.lower()
    if role not in _ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "validation_error", "message": f"Unsupported role '{payload.role}'"},
        )

    next_id = max(existing["id"] for existing in _DEFAULT_USERS.values()) + 1
    user_record = {
        "id": next_id,
        "tenant_id": 1,
        "tenant_slug": "acme",
        "email": email,
        "full_name": payload.full_name,
        "role": role,
        "password_hash": hash_password(payload.password),
        "is_active": True,
        "last_login_at": None,
    }
    _DEFAULT_USERS[email] = user_record
    return {
        "id": user_record["id"],
        "tenant_id": user_record["tenant_id"],
        "email": user_record["email"],
        "full_name": user_record["full_name"],
        "role": user_record["role"],
        "is_active": user_record["is_active"],
        "last_login_at": user_record["last_login_at"],
    }
