from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.get("")
def scoring_root() -> dict[str, str]:
    return {"status": "ok"}
