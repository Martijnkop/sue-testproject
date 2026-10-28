from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/routing", tags=["routing"])


@router.get("")
def routing_root() -> dict[str, str]:
    return {"status": "ok"}
