from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
