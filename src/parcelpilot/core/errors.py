from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    field: str | None = None
    issue: str


class ErrorPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str
    message: str
    details: list[ErrorDetail] = []
    request_id: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    error: ErrorPayload


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return str(value) if value else "unknown"


def _error_payload(code: str, message: str, *, request_id: str, details: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "request_id": request_id,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = _request_id(request)
        detail = exc.detail
        if isinstance(detail, dict):
            code = str(detail.get("code", "http_error"))
            message = str(detail.get("message", "Request failed"))
            details = detail.get("details", [])
        else:
            code = "http_error"
            message = str(detail)
            details = []
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(code, message, request_id=request_id, details=details),
            headers={"X-Request-Id": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = _request_id(request)
        details = [
            {"field": ".".join(str(item) for item in error.get("loc", ())), "issue": error.get("msg", "validation error")}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_error_payload("validation_error", "Request body failed validation", request_id=request_id, details=details),
            headers={"X-Request-Id": request_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id(request)
        return JSONResponse(
            status_code=500,
            content=_error_payload("internal_error", "Internal server error", request_id=request_id),
            headers={"X-Request-Id": request_id},
        )
