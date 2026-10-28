from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("")
def exports_root() -> dict[str, str]:
    return {"status": "ok"}
