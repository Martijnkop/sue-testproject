from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException

from parcelpilot.catalog.api import _CATEGORIES, _PRODUCTS
from parcelpilot.customers.api import _CUSTOMERS
from parcelpilot.orders import repo as order_repo
from parcelpilot.reports.models import Report

_REPORTS: dict[tuple[int, int], dict[str, Any]] = {}
_RUN_SEQUENCE = 0
_GROUP_FIELDS = {"day", "product", "category", "customer"}


def create_sales_report(tenant_id: int, user_id: int, params: dict[str, Any]) -> dict[str, Any]:
    global _RUN_SEQUENCE
    group_by = params["group_by"]
    if group_by not in _GROUP_FIELDS:
        raise HTTPException(status_code=422, detail={"code": "invalid_group_by", "message": "Unsupported group_by value"})
    date_from, date_to = params.get("date_from"), params.get("date_to")
    grouped: dict[str, dict[str, Any]] = {}
    orders_count: dict[str, set[int]] = defaultdict(set)
    for order in order_repo.list_for_tenant(tenant_id):
        placed = order["placed_at"].date()
        if date_from and placed < date_from or date_to and placed > date_to:
            continue
        if order["currency"] != params["currency"]:
            continue
        for item in order.get("items", []):
            product = _PRODUCTS.get(item["sku"], {})
            if group_by == "day":
                key, label = placed.isoformat(), placed.isoformat()
            elif group_by == "product":
                key, label = str(item["sku"]), str(product.get("name", item["sku"]))
            elif group_by == "category":
                category_id = product.get("category_id")
                category = _CATEGORIES.get(category_id) if category_id is not None else None
                key, label = str(category_id or "uncategorized"), str(category.get("name", category_id) if category else "Uncategorized")
            else:
                customer_id = int(order["customer_id"])
                customer = _CUSTOMERS.get(customer_id, {})
                key, label = str(customer_id), str(customer.get("full_name", order.get("customer_name", customer_id)))
            row = grouped.setdefault(key, {
                "group_key": key, "label": label, "orders_count": 0, "units": 0,
                "revenue_cents": 0, "discount_cents": 0, "tax_cents": 0,
            })
            row["units"] += int(item["quantity"])
            row["revenue_cents"] += int(item["unit_price_cents"]) * int(item["quantity"])
            row["discount_cents"] += int(item["discount_cents"])
            row["tax_cents"] += int(item["tax_cents"])
            orders_count[key].add(int(order["id"]))
    rows = []
    for key, row in grouped.items():
        row["orders_count"] = len(orders_count[key])
        if row["revenue_cents"] >= int(params.get("min_revenue_cents", 0)):
            rows.append(row)
    rows.sort(key=lambda row: (-row["revenue_cents"], row["group_key"]))
    top_n = params.get("top_n")
    if top_n is not None:
        rows = rows[:top_n]
    _RUN_SEQUENCE += 1
    run_id = _RUN_SEQUENCE
    summary = {
        "orders_count": len({order_id for row_ids in orders_count.values() for order_id in row_ids}),
        "units": sum(row["units"] for row in rows),
        "revenue_cents": sum(row["revenue_cents"] for row in rows),
    }
    report = Report(run_id, tenant_id, dict(params), rows)
    _REPORTS[(tenant_id, run_id)] = {
        "report": report,
        "created_by": user_id,
        "created_at": datetime.now(timezone.utc),
        "summary": summary,
        "status": "completed",
    }
    return {"run_id": run_id, "status": "completed", "row_count": len(rows), "summary": summary, "created_at": _REPORTS[(tenant_id, run_id)]["created_at"]}


def get_report(tenant_id: int, run_id: int) -> Report | None:
    record = _REPORTS.get((tenant_id, run_id))
    return record["report"] if record is not None else None


def render_page(report: Report, *, sort_by: str, order: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    if sort_by not in {"revenue_cents", "orders_count", "units", "label"}:
        raise HTTPException(status_code=422, detail={"code": "invalid_sort_by", "message": "Unsupported sort_by value"})
    if order not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail={"code": "invalid_order", "message": "order must be asc or desc"})
    report.configure(sort_by, order)
    rows = []
    for index in range(len(report.sorted_rows)):
        row = report.sorted_rows[index]
        if offset <= index < offset + limit:
            rows.append({**row, "rank": index + 1})
    return rows, len(report._rows)
