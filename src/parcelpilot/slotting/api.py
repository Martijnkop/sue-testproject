from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/slotting", tags=["slotting"])


@router.get("")
def slotting_root() -> dict[str, str]:
    return {"status": "ok"}
