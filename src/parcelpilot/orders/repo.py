from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

from parcelpilot.core.logging import configure_logging, log_event
from parcelpilot.orders.schemas import OrderCreate

logger = configure_logging()

_ORDERS: dict[tuple[int, int], dict[str, Any]] = {}
_ORDER_SEQUENCE = 0
_ADDRESS_SEQUENCE = 10000
_ITEM_SEQUENCE = 0
_RESERVATIONS: dict[tuple[int, int], list[tuple[str, str, int]]] = {}


def create_address(address: dict[str, Any], customer_id: int) -> dict[str, Any]:
    global _ADDRESS_SEQUENCE
    _ADDRESS_SEQUENCE += 1
    created = copy.deepcopy(address)
    created["id"] = _ADDRESS_SEQUENCE
    created["customer_id"] = customer_id
    return created


def next_order_id() -> int:
    return max((order_id for _, order_id in _ORDERS), default=0) + 1


def insert(
    tenant_id: int,
    order_data: dict[str, Any],
    original_payload: dict[str, Any],
    reservations: list[tuple[str, str, int]],
) -> dict[str, Any]:
    global _ITEM_SEQUENCE, _ORDER_SEQUENCE
    validation_data = copy.deepcopy(order_data)
    validation_data.pop("shipping_address", None)
    validated = OrderCreate.model_validate(validation_data)
    row = copy.deepcopy(order_data)
    row.update(validated.model_dump(exclude={"items", "shipping_address"}))
    _ORDER_SEQUENCE += 1
    order_id = _ORDER_SEQUENCE
    for item in row["items"]:
        _ITEM_SEQUENCE += 1
        item["id"] = _ITEM_SEQUENCE
    row["id"] = order_id
    row["placed_at"] = row.get("placed_at") or datetime.now(timezone.utc)
    row["updated_at"] = row["placed_at"]
    encoded_payload = json.dumps(original_payload, sort_keys=True, default=str)
    row["raw_payload"] = json.loads(json.dumps(json.loads(encoded_payload), sort_keys=True))
    row["reservations"] = list(reservations)
    _ORDERS[(tenant_id, order_id)] = row
    _RESERVATIONS[(tenant_id, order_id)] = list(reservations)
    log_event(logger, "order.inserted", {"order_id": order_id, "tenant_id": tenant_id})
    return get(tenant_id, order_id)  # return an isolated representation


def get(tenant_id: int, order_id: int) -> dict[str, Any] | None:
    order = _ORDERS.get((tenant_id, order_id))
    return copy.deepcopy(order) if order is not None else None


def list_for_tenant(tenant_id: int) -> list[dict[str, Any]]:
    return [
        copy.deepcopy(order)
        for (order_tenant_id, _), order in _ORDERS.items()
        if order_tenant_id == tenant_id
    ]


def update_status(
    tenant_id: int,
    order_id: int,
    new_status: str,
    reason: str,
) -> dict[str, Any] | None:
    order = _ORDERS.get((tenant_id, order_id))
    if order is None:
        return None
    order["status"] = new_status
    order["updated_at"] = datetime.now(timezone.utc)
    log_event(
        logger,
        "order.status_updated",
        {"order_id": order_id, "status": new_status, "reason": reason},
    )
    return get(tenant_id, order_id)


def reservations_for(tenant_id: int, order_id: int) -> list[tuple[str, str, int]]:
    return list(_RESERVATIONS.get((tenant_id, order_id), []))


def update_imported_details(
    tenant_id: int,
    order_id: int,
    *,
    shipping_address: dict[str, Any],
    item_prices: dict[str, int],
) -> None:
    order = _ORDERS.get((tenant_id, order_id))
    if order is None:
        return
    order["shipping_address"].update(copy.deepcopy(shipping_address))
    for item in order["items"]:
        price = item_prices.get(item["sku"])
        if price is not None:
            item["unit_price_cents"] = price
            item["line_total_cents"] = (
                price * int(item["quantity"]) - int(item["discount_cents"]) + int(item["tax_cents"])
            )
    order["subtotal_cents"] = sum(int(item["unit_price_cents"]) * int(item["quantity"]) for item in order["items"])
    order["discount_cents"] = sum(int(item["discount_cents"]) for item in order["items"])
    order["tax_cents"] = sum(int(item["tax_cents"]) for item in order["items"])
    order["total_cents"] = (
        order["subtotal_cents"] - order["discount_cents"] + order["tax_cents"] + int(order["shipping_cents"])
    )
    order["raw_payload"]["shipping_address"] = copy.deepcopy(order["shipping_address"])
