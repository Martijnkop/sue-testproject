from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from parcelpilot.core.pagination import normalize_pagination

router = APIRouter(prefix="/warehouses", tags=["warehouses"])

_WAREHOUSES: dict[int, dict[str, Any]] = {}
_WAREHOUSE_SEQUENCE = 1


class WarehouseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    name: str
    region: str | None = None
    address: dict[str, Any] | None = None
    is_active: bool = True


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize_code(code: str) -> str:
    value = code.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,12}", value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "validation_error", "message": "Warehouse code must be 2-12 uppercase alphanumeric characters"},
        )
    return value


@router.post("")
def create_warehouse(payload: WarehouseCreateRequest) -> dict[str, Any]:
    code = _sanitize_code(payload.code)
    if any(item["code"] == code for item in _WAREHOUSES.values()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "warehouse_code_exists", "message": "Warehouse code already exists"},
        )

    warehouse_id = max((_WAREHOUSES.keys()), default=0) + 1
    warehouse = {
        "id": warehouse_id,
        "code": code,
        "name": payload.name,
        "region": payload.region,
        "address": payload.address or {"line1": "", "city": "", "country_code": "DE"},
        "is_active": payload.is_active,
        "created_at": _now(),
    }
    _WAREHOUSES[warehouse_id] = warehouse
    return warehouse


@router.get("")
def list_warehouses(limit: int | None = None, offset: int | None = None) -> dict[str, Any]:
    resolved_limit, resolved_offset = normalize_pagination(limit, offset)
    items = [dict(warehouse) for warehouse in sorted(_WAREHOUSES.values(), key=lambda item: item["id"]) ]
    page = items[resolved_offset : resolved_offset + resolved_limit]
    return {"items": page, "total": len(items), "limit": resolved_limit, "offset": resolved_offset}
