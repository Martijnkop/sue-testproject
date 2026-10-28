from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/shipments", tags=["shipments"])


@router.get("")
def shipments_root() -> dict[str, str]:
    return {"status": "ok"}
