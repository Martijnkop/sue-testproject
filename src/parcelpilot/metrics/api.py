from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
def metrics_root() -> dict[str, str]:
    return {"status": "ok"}
