from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone
from typing import Any, Mapping

from fastapi import HTTPException, status

from parcelpilot.catalog.api import _PRODUCTS, _STOCK, _stock_available
from parcelpilot.catalog.keys import SkuKey
from parcelpilot.core.logging import configure_logging, log_event
from parcelpilot.customers.api import _CUSTOMERS
from parcelpilot.fraud.screening import register_order_snapshot, screen_order
from parcelpilot.orders import repo
from parcelpilot.orders.schemas import OrderCreate, copy_payload, deepcopy_payload
from parcelpilot.pricing.api import _DISCOUNTS
from parcelpilot.pricing.service import price_line
from parcelpilot.tax.service import tax_for_line
from parcelpilot.warehouses.api import _WAREHOUSES

DEFAULT_SHIPPING_CENTS = 495
logger = configure_logging()
_DEFAULT_TAX_RULES = [
    {
        "id": 0,
        "country_code": "DE",
        "region": None,
        "category_id": None,
        "rate_bps": 1900,
        "threshold_cents": None,
        "priority": 0,
        "valid_from": date(1900, 1, 1),
        "valid_to": None,
    }
]
_TAX_RULES: dict[int, list[dict[str, Any]]] = {}
_ALLOWED_TRANSITIONS = {
    "pending": {"confirmed", "fraud_review", "cancelled"},
    "fraud_review": {"confirmed", "cancelled"},
    "confirmed": {"picking", "cancelled"},
    "picking": {"shipped", "cancelled"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


def _http_error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message},
    )


def _address_for_order(payload: OrderCreate, customer: dict[str, Any]) -> dict[str, Any]:
    if payload.shipping_address_id is not None:
        address = next(
            (
                item
                for item in customer.get("addresses", [])
                if item.get("id") == payload.shipping_address_id
            ),
            None,
        )
        if address is None:
            raise _http_error("address_not_found", "Shipping address not found for customer", 404)
        result = copy.deepcopy(address)
        required = ("line1", "city", "postal_code", "country_code")
        for field in required:
            value = result.get(field)
            if not isinstance(value, str) or not value.strip():
                raise _http_error("address_incomplete", "Shipping address is incomplete", 422)
            result[field] = value.strip()
        country_code = result["country_code"].upper()
        if len(country_code) != 2 or not country_code.isalpha():
            raise _http_error("address_incomplete", "Shipping address country is invalid", 422)
        result["country_code"] = country_code
        return result

    inline_address = payload.shipping_address
    if inline_address is None:
        raise _http_error("address_not_found", "Shipping address is required", 422)
    raw_address = inline_address.model_dump()
    city_key = raw_address["city"].strip().lower()
    coordinates = {
        "leipzig": (51.3397, 12.3731),
        "berlin": (52.52, 13.405),
        "hamburg": (53.5511, 9.9937),
        "munich": (48.1351, 11.582),
    }
    latitude, longitude = coordinates.get(city_key, (0.0, 0.0))
    address = {
        **raw_address,
        "latitude": latitude,
        "longitude": longitude,
        "is_default": False,
        "normalized_at": None,
    }
    return repo.create_address(address, int(customer["id"]))


def _find_reservations(
    requested_quantities: dict[str, int],
) -> list[tuple[str, str, int]]:
    active_codes = sorted(
        warehouse["code"]
        for warehouse in _WAREHOUSES.values()
        if warehouse.get("is_active", True)
    )
    for warehouse_code in active_codes:
        allocations: list[tuple[str, str, int]] = []
        for sku, quantity in requested_quantities.items():
            stock = _STOCK.get(SkuKey(warehouse_code, sku))
            if stock is None or _stock_available(stock) < quantity:
                break
            allocations.append((warehouse_code, sku, quantity))
        else:
            return allocations
    raise _http_error("insufficient_stock", "No active warehouse can fulfill the order", 409)


def _reserve_stock(reservations: list[tuple[str, str, int]]) -> None:
    for warehouse_code, sku, quantity in reservations:
        stock = _STOCK[SkuKey(warehouse_code, sku)]
        stock["reserved"] = int(stock.get("reserved", 0)) + quantity
        stock["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _release_stock(reservations: list[tuple[str, str, int]]) -> None:
    for warehouse_code, sku, quantity in reservations:
        stock = _STOCK.get(SkuKey(warehouse_code, sku))
        if stock is None:
            continue
        stock["reserved"] = max(0, int(stock.get("reserved", 0)) - quantity)
        stock["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _price_items(
    payload: OrderCreate,
    address: dict[str, Any],
    tenant_id: int,
    unit_price_overrides: Mapping[str, int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int], set[str]]:
    discounts_by_code = _DISCOUNTS.get(tenant_id, {})
    discounts = []
    seen_codes: set[str] = set()
    for code in payload.discount_codes:
        if code in seen_codes:
            continue
        seen_codes.add(code)
        discount = discounts_by_code.get(code)
        if discount is None:
            raise _http_error("discount_not_found", f"Discount code {code!r} is not available", 422)
        discounts.append(discount)

    requested_at = datetime.now(timezone.utc)
    tax_rules = _TAX_RULES.get(tenant_id, _DEFAULT_TAX_RULES)
    product_discounts = [discount for discount in discounts if discount["kind"] != "shipping"]
    line_items: list[dict[str, Any]] = []
    subtotal_cents = 0
    discount_cents = 0
    tax_cents = 0
    applied_discount_codes: set[str] = set()
    for item in payload.items:
        product = _PRODUCTS.get(item.sku)
        if product is None or not product.get("is_active", True):
            raise _http_error("sku_not_found", f"Product {item.sku!r} is not available", 404)
        currency = str(product.get("currency", "EUR")).upper()
        if currency != payload.currency:
            raise _http_error("currency_mismatch", "All products must use the order currency", 422)
        unit_price = int((unit_price_overrides or {}).get(item.sku, product.get("base_price_cents", 0)))
        line_subtotal = unit_price * item.quantity
        line_pricing = price_line(
            unit_price,
            item.quantity,
            product_discounts,
            requested_at=requested_at,
            applied_codes=applied_discount_codes,
        )
        item_discount = line_pricing["discount_cents"]
        category_id = product.get("category_id")
        item_tax = tax_for_line(
            line_subtotal - item_discount,
            tax_rules,
            country_code=address.get("country_code"),
            region=address.get("region"),
            category_id=int(category_id) if category_id is not None else None,
            as_of=requested_at.date(),
        )
        line_total = line_subtotal - item_discount + item_tax
        line_items.append(
            {
                "id": 0,
                "product_id": int(product["id"]),
                "sku": item.sku,
                "quantity": item.quantity,
                "unit_price_cents": unit_price,
                "discount_cents": item_discount,
                "tax_cents": item_tax,
                "line_total_cents": line_total,
            }
        )
        subtotal_cents += line_subtotal
        discount_cents += item_discount
        tax_cents += item_tax

    shipping_pricing = price_line(
        0,
        1,
        [discount for discount in discounts if discount["kind"] == "shipping"],
        requested_at=requested_at,
        shipping_cents=DEFAULT_SHIPPING_CENTS,
        applied_codes=applied_discount_codes,
    )
    discount_cents += shipping_pricing["discount_cents"]
    shipping_cents = DEFAULT_SHIPPING_CENTS
    totals = {
        "subtotal_cents": subtotal_cents,
        "discount_cents": discount_cents,
        "tax_cents": tax_cents,
        "shipping_cents": shipping_cents,
        "total_cents": subtotal_cents - discount_cents + tax_cents + shipping_cents,
    }
    return line_items, totals, applied_discount_codes


def _screen_order(
    payload: OrderCreate,
    customer: dict[str, Any],
    address: dict[str, Any],
    tenant_id: int,
    order_id: int,
) -> dict[str, Any]:
    snapshot = {
        "email": customer.get("email"),
        "full_name": customer.get("full_name"),
        "phone": customer.get("phone"),
        "ip_address": payload.client_ip,
        "shipping_address": address,
    }
    register_order_snapshot(tenant_id, order_id, snapshot)
    return screen_order(snapshot, tenant_id, order_id)


def create_order(
    serialized_payload: str,
    tenant_id: int,
    *,
    source: str = "api",
    unit_price_overrides: Mapping[str, int] | None = None,
    placed_at: datetime | None = None,
) -> dict[str, Any]:
    raw_payload = json.loads(serialized_payload)
    request = OrderCreate.model_validate(raw_payload)
    payload_dict = copy_payload(request.model_dump())
    payload_copy = deepcopy_payload(payload_dict)
    payload = OrderCreate.model_validate(payload_copy)
    log_event(logger, "order.create", {"customer_id": payload.customer_id})

    customer = _CUSTOMERS.get(payload.customer_id)
    if customer is None:
        raise _http_error("customer_not_found", "Customer not found", 404)
    if payload.external_ref is not None:
        if any(
            order["external_ref"] == payload.external_ref
            for order in repo.list_for_tenant(tenant_id)
        ):
            raise _http_error("duplicate_external_ref", "External reference already exists", 409)

    address = _address_for_order(payload, customer)
    line_items, totals, applied_discount_codes = _price_items(payload, address, tenant_id, unit_price_overrides)
    requested_quantities = {item.sku: item.quantity for item in payload.items}
    reservations = _find_reservations(requested_quantities)

    order_id = repo.next_order_id()
    fraud = _screen_order(payload, customer, address, tenant_id, order_id)
    order_status = "confirmed" if fraud["decision"] == "allow" else "fraud_review"
    order_data: dict[str, Any] = {
        "tenant_id": tenant_id,
        "customer_id": payload.customer_id,
        "shipping_address_id": int(address["id"]),
        "external_ref": payload.external_ref,
        "source": source,
        "status": order_status,
        "currency": payload.currency,
        "subtotal_cents": totals["subtotal_cents"],
        "discount_cents": totals["discount_cents"],
        "tax_cents": totals["tax_cents"],
        "shipping_cents": totals["shipping_cents"],
        "total_cents": totals["total_cents"],
        "fraud_decision": fraud["decision"],
        "fraud_score": fraud["score"],
        "client_ip": payload.client_ip,
        "notes": payload.notes,
        "raw_payload": payload_dict,
        "placed_at": placed_at or datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "items": line_items,
        "shipping_address": address,
        "fraud": {"decision": fraud["decision"], "score": fraud["score"]},
        "shipments": [],
    }
    serialized_original = json.dumps(raw_payload, sort_keys=True, default=str)
    original_for_repository = json.loads(serialized_original)
    stored = repo.insert(tenant_id, order_data, original_for_repository, reservations)
    _reserve_stock(reservations)
    for code in applied_discount_codes:
        discount = _DISCOUNTS[tenant_id][code]
        discount["used_count"] = int(discount["used_count"]) + 1
    customer["order_count"] = int(customer.get("order_count", 0)) + 1
    return stored


def list_orders(
    tenant_id: int,
    *,
    statuses: list[str] | None,
    customer_id: int | None,
    source: str | None,
    placed_from: date | None,
    placed_to: date | None,
    min_total_cents: int | None,
    max_total_cents: int | None,
    sort: str,
) -> list[dict[str, Any]]:
    orders = repo.list_for_tenant(tenant_id)
    if statuses:
        orders = [order for order in orders if order["status"] in statuses]
    if customer_id is not None:
        orders = [order for order in orders if order["customer_id"] == customer_id]
    if source is not None:
        orders = [order for order in orders if order["source"] == source]
    if placed_from is not None:
        orders = [order for order in orders if order["placed_at"].date() >= placed_from]
    if placed_to is not None:
        orders = [order for order in orders if order["placed_at"].date() <= placed_to]
    if min_total_cents is not None:
        orders = [order for order in orders if order["total_cents"] >= min_total_cents]
    if max_total_cents is not None:
        orders = [order for order in orders if order["total_cents"] <= max_total_cents]

    field = sort[1:] if sort.startswith("-") else sort
    reverse = sort.startswith("-")
    orders.sort(key=lambda order: (order[field], order["id"]), reverse=reverse)
    return orders


def update_order_status(
    tenant_id: int,
    order_id: int,
    new_status: str,
    reason: str,
) -> dict[str, Any]:
    order = repo.get(tenant_id, order_id)
    if order is None:
        raise _http_error("order_not_found", "Order not found", 404)
    allowed = _ALLOWED_TRANSITIONS.get(order["status"], set())
    if new_status not in allowed:
        raise _http_error("invalid_transition", "Order status transition is not allowed", 409)
    updated = repo.update_status(tenant_id, order_id, new_status, reason)
    if updated is None:
        raise _http_error("order_not_found", "Order not found", 404)
    if new_status == "cancelled":
        _release_stock(repo.reservations_for(tenant_id, order_id))
    return updated
