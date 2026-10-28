from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError

from parcelpilot.core.logging import configure_logging, log_event
from parcelpilot.core.pagination import normalize_pagination
from parcelpilot.core.security import require_roles
from parcelpilot.orders import repo, service
from parcelpilot.orders.schemas import OrderCreate, OrderStatusUpdate, render_order

router = APIRouter(prefix="/orders", tags=["orders"])
logger = logging.getLogger(__name__)
event_logger = configure_logging()

OrderStatusValue = Literal[
    "pending",
    "fraud_review",
    "confirmed",
    "picking",
    "shipped",
    "delivered",
    "cancelled",
]
OrderSourceValue = Literal["api", "bulk_import"]
OrderSortValue = Literal["placed_at", "-placed_at", "total_cents", "-total_cents"]


def _tenant_id(user: dict[str, Any]) -> int:
    return int(user["tenant_id"])


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _item_response(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "product_id": item["product_id"],
        "sku": item["sku"],
        "quantity": item["quantity"],
        "unit_price_cents": item["unit_price_cents"],
        "discount_cents": item["discount_cents"],
        "tax_cents": item["tax_cents"],
        "line_total_cents": item["line_total_cents"],
    }


def _address_response(address: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": address["id"],
        "line1": address["line1"],
        "line2": address.get("line2"),
        "city": address["city"],
        "region": address.get("region"),
        "postal_code": address["postal_code"],
        "country_code": address["country_code"],
        "latitude": address.get("latitude"),
        "longitude": address.get("longitude"),
        "is_default": bool(address.get("is_default", False)),
        "normalized_at": address.get("normalized_at"),
    }


def _summary(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": order["id"],
        "external_ref": order.get("external_ref"),
        "customer_id": order["customer_id"],
        "status": order["status"],
        "currency": order["currency"],
        "total_cents": order["total_cents"],
        "fraud_decision": order.get("fraud_decision"),
        "placed_at": _timestamp(order["placed_at"]),
    }


def _response(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": order["id"],
        "external_ref": order.get("external_ref"),
        "customer_id": order["customer_id"],
        "status": order["status"],
        "source": order["source"],
        "currency": order["currency"],
        "items": [_item_response(item) for item in order["items"]],
        "subtotal_cents": order["subtotal_cents"],
        "discount_cents": order["discount_cents"],
        "tax_cents": order["tax_cents"],
        "shipping_cents": order["shipping_cents"],
        "total_cents": order["total_cents"],
        "shipping_address": _address_response(order["shipping_address"]),
        "fraud": {
            "decision": order["fraud"]["decision"],
            "score": order["fraud"]["score"],
        },
        "notes": order.get("notes"),
        "placed_at": _timestamp(order["placed_at"]),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    user: dict[str, Any] = Depends(require_roles("admin", "ops")),
) -> dict[str, Any]:
    raw_payload = payload.model_dump(mode="json")
    try:
        validated = OrderCreate.model_validate(raw_payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "validation_error", "message": str(exc)},
        ) from exc
    serialized_payload = json.dumps(validated.model_dump(mode="json"), sort_keys=True)
    log_event(event_logger, "order.request_received", {"customer_id": validated.customer_id})
    order = service.create_order(serialized_payload, _tenant_id(user))
    logger.debug(f"order state: {render_order(order)}")
    return _response(order)


@router.get("")
def list_orders(
    order_status: list[OrderStatusValue] | None = Query(default=None, alias="status"),
    customer_id: int | None = Query(default=None, gt=0),
    source: OrderSourceValue | None = None,
    placed_from: date | None = None,
    placed_to: date | None = None,
    min_total_cents: int | None = Query(default=None, ge=0),
    max_total_cents: int | None = Query(default=None, ge=0),
    sort: OrderSortValue = "-placed_at",
    limit: int | None = Query(default=None, ge=1),
    offset: int | None = Query(default=None, ge=0),
    user: dict[str, Any] = Depends(require_roles("admin", "ops", "analyst", "viewer")),
) -> dict[str, Any]:
    if placed_from is not None and placed_to is not None and placed_to < placed_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "validation_error", "message": "placed_to must not precede placed_from"},
        )
    if (
        min_total_cents is not None
        and max_total_cents is not None
        and max_total_cents < min_total_cents
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "validation_error", "message": "max_total_cents must be at least min_total_cents"},
        )
    orders = service.list_orders(
        _tenant_id(user),
        statuses=list(order_status) if order_status is not None else None,
        customer_id=customer_id,
        source=source,
        placed_from=placed_from,
        placed_to=placed_to,
        min_total_cents=min_total_cents,
        max_total_cents=max_total_cents,
        sort=sort,
    )
    resolved_limit, resolved_offset = normalize_pagination(limit, offset)
    page = orders[resolved_offset : resolved_offset + resolved_limit]
    return {
        "items": [_summary(order) for order in page],
        "total": len(orders),
        "limit": resolved_limit,
        "offset": resolved_offset,
    }


@router.get("/{order_id}")
def get_order(
    order_id: int,
    user: dict[str, Any] = Depends(require_roles("admin", "ops", "analyst", "viewer")),
) -> dict[str, Any]:
    order = repo.get(_tenant_id(user), order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "order_not_found", "message": "Order not found"},
        )
    response = _response(order)
    response["shipments"] = order.get("shipments", [])
    return response


@router.patch("/{order_id}/status")
def patch_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    user: dict[str, Any] = Depends(require_roles("admin", "ops")),
) -> dict[str, Any]:
    order = service.update_order_status(
        _tenant_id(user),
        order_id,
        payload.status,
        payload.reason,
    )
    logger.debug(f"order state: {render_order(order)}")
    return _summary(order)
