from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest
from fastapi import HTTPException

from parcelpilot.catalog import api as catalog_api
from parcelpilot.catalog.keys import SkuKey
from parcelpilot.customers import api as customers_api
from parcelpilot.fraud.lookup import reload_blocklists
from parcelpilot.orders import api as orders_api
from parcelpilot.orders import repo, service
from parcelpilot.orders.schemas import OrderCreate
from parcelpilot.pricing import api as pricing_api
from parcelpilot.tests.bench import load_benchmark_threshold
from parcelpilot.tests.oracle_helpers import load_oracle
from parcelpilot.warehouses import api as warehouses_api


def _configure_order_state(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    products = {
        "TEST-1": {
            "id": 40,
            "sku": "TEST-1",
            "name": "Test item",
            "base_price_cents": 1000,
            "currency": "EUR",
            "category_id": 7,
            "is_active": True,
        }
    }
    stock = {
        SkuKey("WH1", "TEST-1"): {
            "warehouse_code": "WH1",
            "sku": "TEST-1",
            "on_hand": 10000,
            "reserved": 0,
            "updated_at": "2026-10-10T00:00:00Z",
        }
    }
    warehouses = {1: {"id": 1, "code": "WH1", "is_active": True}}
    customers = {
        118: {
            "id": 118,
            "email": "buyer@example.com",
            "full_name": "Buyer One",
            "phone": "+49 111 222333",
            "addresses": [],
            "order_count": 0,
        }
    }
    discounts = {
        1: {
            "id": 1,
            "code": "TENOFF",
            "kind": "percent",
            "value": 1000,
            "min_subtotal_cents": 0,
            "stack_group": None,
            "max_uses": None,
            "used_count": 0,
            "is_active": True,
            "valid_from": None,
            "valid_to": None,
        }
    }
    tax_rules = [
        {
            "id": 1,
            "country_code": "DE",
            "region": None,
            "category_id": None,
            "rate_bps": 1900,
            "threshold_cents": None,
            "priority": 0,
            "valid_from": date(2020, 1, 1),
            "valid_to": None,
        }
    ]
    monkeypatch.setattr(catalog_api, "_PRODUCTS", products)
    monkeypatch.setattr(catalog_api, "_STOCK", stock)
    monkeypatch.setattr(service, "_PRODUCTS", products)
    monkeypatch.setattr(service, "_STOCK", stock)
    monkeypatch.setattr(customers_api, "_CUSTOMERS", customers)
    monkeypatch.setattr(service, "_CUSTOMERS", customers)
    monkeypatch.setattr(warehouses_api, "_WAREHOUSES", warehouses)
    monkeypatch.setattr(service, "_WAREHOUSES", warehouses)
    monkeypatch.setattr(pricing_api, "_DISCOUNTS", {1: discounts})
    monkeypatch.setattr(service, "_DISCOUNTS", {1: discounts})
    monkeypatch.setattr(service, "_TAX_RULES", {1: tax_rules})
    monkeypatch.setattr(repo, "_ORDERS", {})
    monkeypatch.setattr(repo, "_RESERVATIONS", {})
    monkeypatch.setattr(repo, "_ORDER_SEQUENCE", 0)
    monkeypatch.setattr(repo, "_ITEM_SEQUENCE", 0)
    monkeypatch.setattr(repo, "_ADDRESS_SEQUENCE", 10000)
    reload_blocklists([])
    return {"customers": customers, "discounts": discounts, "stock": stock}


def _order_payload() -> OrderCreate:
    return OrderCreate.model_validate(
        {
            "customer_id": 118,
            "currency": "EUR",
            "items": [{"sku": "test-1", "quantity": 1}],
            "shipping_address": {
                "line1": "Karl-Heine-Str. 12",
                "city": "Leipzig",
                "region": "SN",
                "postal_code": "04229",
                "country_code": "DE",
            },
            "discount_codes": ["tenoff"],
        }
    )


def _semantic_result(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "customer_id": order["customer_id"],
        "status": order["status"],
        "source": order["source"],
        "currency": order["currency"],
        "items": [
            {
                key: item[key]
                for key in (
                    "product_id",
                    "sku",
                    "quantity",
                    "unit_price_cents",
                    "discount_cents",
                    "tax_cents",
                    "line_total_cents",
                )
            }
            for item in order["items"]
        ],
        "subtotal_cents": order["subtotal_cents"],
        "discount_cents": order["discount_cents"],
        "tax_cents": order["tax_cents"],
        "shipping_cents": order["shipping_cents"],
        "total_cents": order["total_cents"],
        "fraud_decision": order["fraud_decision"],
        "fraud_score": order["fraud_score"],
    }


@pytest.mark.oracle
def test_two_hundred_order_requests_match_h3_oracle_and_keep_raw_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_order_state(monkeypatch)
    payload = _order_payload()
    expected = load_oracle("H3")

    for _ in range(200):
        raw_payload = payload.model_dump(mode="json")
        order = service.create_order(json.dumps(raw_payload, sort_keys=True), 1)
        assert _semantic_result(order) == expected
        assert order["raw_payload"] == raw_payload


@pytest.mark.tripwire
def test_order_endpoint_preserves_layered_validation_serialization_and_debug_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_order_state(monkeypatch)
    payload = _order_payload()
    counters = {"loads": 0, "dumps": 0, "validations": 0, "renders": 0}
    original_loads = json.loads
    original_dumps = json.dumps
    original_validate = OrderCreate.model_validate
    original_render = orders_api.render_order

    def counted_loads(*args: Any, **kwargs: Any) -> Any:
        counters["loads"] += 1
        return original_loads(*args, **kwargs)

    def counted_dumps(*args: Any, **kwargs: Any) -> Any:
        counters["dumps"] += 1
        return original_dumps(*args, **kwargs)

    def counted_validate(cls: type[OrderCreate], value: Any, **kwargs: Any) -> OrderCreate:
        counters["validations"] += 1
        return original_validate(value, **kwargs)

    def counted_render(order: dict[str, Any]) -> str:
        counters["renders"] += 1
        return original_render(order)

    monkeypatch.setattr(json, "loads", counted_loads)
    monkeypatch.setattr(json, "dumps", counted_dumps)
    monkeypatch.setattr(OrderCreate, "model_validate", classmethod(counted_validate))
    monkeypatch.setattr(orders_api, "render_order", counted_render)

    response = orders_api.create_order(payload, {"tenant_id": 1, "role": "admin"})

    assert response["total_cents"] == 1566
    assert counters["loads"] >= 3
    assert counters["dumps"] >= 3
    assert counters["validations"] >= 3
    assert counters["renders"] == 1


def test_order_list_filters_sorts_and_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_order_state(monkeypatch)
    payload = _order_payload()
    first = service.create_order(json.dumps(payload.model_dump(mode="json")), 1)
    first["total_cents"] = 2000
    repo._ORDERS[(1, first["id"])]["total_cents"] = 2000
    second = service.create_order(json.dumps(payload.model_dump(mode="json")), 1)
    second["total_cents"] = 1000
    repo._ORDERS[(1, second["id"])]["total_cents"] = 1000

    rows = service.list_orders(
        1,
        statuses=["confirmed"],
        customer_id=118,
        source="api",
        placed_from=None,
        placed_to=None,
        min_total_cents=1000,
        max_total_cents=2000,
        sort="total_cents",
    )

    assert [order["total_cents"] for order in rows] == [1000, 2000]


def test_cancelling_an_order_releases_reserved_stock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _configure_order_state(monkeypatch)
    payload = _order_payload()
    order = service.create_order(json.dumps(payload.model_dump(mode="json")), 1)
    stock = state["stock"][SkuKey("WH1", "TEST-1")]
    assert stock["reserved"] == 1

    cancelled = service.update_order_status(1, order["id"], "cancelled", "Customer request")

    assert cancelled["status"] == "cancelled"
    assert stock["reserved"] == 0
    with pytest.raises(HTTPException) as error:
        service.update_order_status(1, order["id"], "confirmed", "Attempt reopen")
    assert error.value.detail["code"] == "invalid_transition"


@pytest.mark.bench
def test_order_creation_benchmark(benchmark: pytest.BenchmarkFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_order_state(monkeypatch)
    payload = _order_payload().model_dump(mode="json")
    assert load_benchmark_threshold("P3") == 1.3

    def create_fixed_orders() -> int:
        for _ in range(500):
            service.create_order(json.dumps(payload, sort_keys=True), 1)
        return len(repo.list_for_tenant(1))

    benchmark.pedantic(create_fixed_orders, rounds=1, iterations=1)
    assert len(repo.list_for_tenant(1)) == 500
