from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from parcelpilot.core.pagination import normalize_pagination
from parcelpilot.core.security import require_roles
from parcelpilot.fraud.repository import add_entries, list_entries, remove_entry, serialize_entry
from parcelpilot.fraud.screening import get_order_snapshot, screen_order

router = APIRouter(prefix="/fraud", tags=["fraud"])

BlocklistType = Literal["email", "ip", "address", "name", "phone"]


class BlocklistEntryInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entry_type: BlocklistType
    value: str = Field(min_length=1, max_length=320)
    reason: str = Field(min_length=1, max_length=500)
    expires_at: datetime | None = None

    @field_validator("value", "reason")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_normalized_value(self) -> BlocklistEntryInput:
        if self.entry_type == "ip":
            try:
                ipaddress.ip_address(self.value)
            except ValueError as exc:
                raise ValueError("value must be a valid IP address") from exc
        if self.entry_type == "phone" and not any(character.isdigit() for character in self.value):
            raise ValueError("phone value must contain digits")
        return self


class BlocklistCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entries: list[BlocklistEntryInput] = Field(max_length=10000)


class FraudScreenRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_id: int | None = Field(default=None, gt=0)
    email: str | None = None
    ip_address: str | None = None
    full_name: str | None = None
    phone: str | None = None
    shipping_address: dict[str, Any] | str | None = None

    @model_validator(mode="after")
    def validate_screen_source(self) -> FraudScreenRequest:
        inline_values = (
            self.email,
            self.ip_address,
            self.full_name,
            self.phone,
            self.shipping_address,
        )
        has_inline = any(value is not None for value in inline_values)
        if (self.order_id is None) == (not has_inline):
            raise ValueError("Provide either order_id or an inline order payload")
        return self


class FraudScreenBatchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_ids: list[int] = Field(min_length=1, max_length=5000)

    @field_validator("order_ids")
    @classmethod
    def validate_order_ids(cls, value: list[int]) -> list[int]:
        if any(order_id <= 0 for order_id in value):
            raise ValueError("order_ids must be positive")
        return value


def _tenant_id(user: dict[str, Any]) -> int:
    return int(user["tenant_id"])


@router.get("/blocklist")
def get_blocklist(
    entry_type: BlocklistType | None = None,
    q: str | None = Query(default=None, max_length=512),
    include_expired: bool = False,
    limit: int | None = None,
    offset: int | None = None,
    user: dict[str, Any] = Depends(require_roles("admin", "ops", "analyst")),
) -> dict[str, Any]:
    tenant_id = _tenant_id(user)
    items = list_entries(tenant_id, include_expired=include_expired)
    if entry_type is not None:
        items = [entry for entry in items if entry["entry_type"] == entry_type]
    if q:
        query = q.casefold()
        items = [entry for entry in items if query in entry["value"].casefold()]
    items.sort(key=lambda entry: entry["id"])
    resolved_limit, resolved_offset = normalize_pagination(limit, offset)
    page = items[resolved_offset : resolved_offset + resolved_limit]
    return {
        "items": [serialize_entry(entry) for entry in page],
        "total": len(items),
        "limit": resolved_limit,
        "offset": resolved_offset,
    }


@router.post("/blocklist", status_code=status.HTTP_201_CREATED)
def create_blocklist_entries(
    payload: BlocklistCreateRequest,
    user: dict[str, Any] = Depends(require_roles("admin")),
) -> dict[str, int]:
    created, skipped = add_entries(
        _tenant_id(user),
        [entry.model_dump() for entry in payload.entries],
    )
    return {"created": created, "skipped_duplicates": skipped}


@router.delete("/blocklist/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_blocklist_entry(
    entry_id: int,
    user: dict[str, Any] = Depends(require_roles("admin")),
) -> Response:
    if not remove_entry(_tenant_id(user), entry_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "blocklist_entry_not_found", "message": "Blocklist entry not found"},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/screen")
def screen_one(
    payload: FraudScreenRequest,
    user: dict[str, Any] = Depends(require_roles("admin", "ops")),
) -> dict[str, Any]:
    tenant_id = _tenant_id(user)
    order_id = payload.order_id
    if order_id is not None:
        order = get_order_snapshot(tenant_id, order_id)
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "order_not_found", "message": "Order not found"},
            )
    else:
        order = payload.model_dump(exclude={"order_id"}, exclude_none=True)

    started_at = perf_counter()
    result = screen_order(order, tenant_id, order_id)
    result["duration_ms"] = int((perf_counter() - started_at) * 1000)
    return result


@router.post("/screen/batch")
def screen_batch(
    payload: FraudScreenBatchRequest,
    user: dict[str, Any] = Depends(require_roles("admin", "ops")),
) -> dict[str, Any]:
    tenant_id = _tenant_id(user)
    orders: list[tuple[int, dict[str, Any]]] = []
    for order_id in payload.order_ids:
        order = get_order_snapshot(tenant_id, order_id)
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "order_not_found", "message": f"Order {order_id} not found"},
            )
        orders.append((order_id, order))

    started_at = perf_counter()
    results = []
    for order_id, order in orders:
        result = screen_order(order, tenant_id, order_id)
        results.append(
            {
                "order_id": order_id,
                "decision": result["decision"],
                "score": result["score"],
                "match_count": len(result["matches"]),
            }
        )
    return {
        "results": results,
        "duration_ms": int((perf_counter() - started_at) * 1000),
    }
