from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from parcelpilot.catalog.api import _PRODUCTS
from parcelpilot.orders import repo as order_repo

_SUMMARIES: dict[tuple[int, date, str], dict[str, Any]] = {}


def compute_range(tenant_id: int, date_from: date, date_to: date, currency: str) -> pd.DataFrame:
    totals: dict[tuple[date, int | None], dict[str, int]] = {}
    for order in order_repo.list_for_tenant(tenant_id):
        summary_date = order["placed_at"].date()
        if summary_date < date_from or summary_date > date_to or order["currency"] != currency:
            continue
        for item in order.get("items", []):
            product = _PRODUCTS.get(item["sku"], {})
            category_id = product.get("category_id")
            key = (summary_date, int(category_id) if category_id is not None else None)
            row = totals.setdefault(key, {"orders_count": 0, "items_count": 0, "gross_cents": 0, "discount_cents": 0, "tax_cents": 0})
            row["orders_count"] += 1
            row["items_count"] += int(item["quantity"])
            row["gross_cents"] += int(item["unit_price_cents"]) * int(item["quantity"])
            row["discount_cents"] += int(item["discount_cents"])
            row["tax_cents"] += int(item["tax_cents"])

    df = pd.DataFrame(columns=["summary_date", "category_id", "orders_count", "items_count", "gross_cents", "discount_cents", "tax_cents"])
    for (summary_date, category_id), values in totals.items():
        row = {"summary_date": summary_date, "category_id": category_id, **values}
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    return df


def compute_daily(tenant_id: int, date_from: date, date_to: date, currency: str, recompute: bool) -> tuple[list[dict[str, Any]], int]:
    existing_by_date = {
        stored_date: value for (stored_tenant, stored_date, stored_currency), value in _SUMMARIES.items()
        if stored_tenant == tenant_id and stored_currency == currency and date_from <= stored_date <= date_to
    }
    frame = compute_range(tenant_id, date_from, date_to, currency)
    summaries: list[dict[str, Any]] = []
    written = 0
    if not frame.empty:
        order_ids_by_date: dict[date, set[int]] = defaultdict(set)
        for order in order_repo.list_for_tenant(tenant_id):
            order_date = order["placed_at"].date()
            if date_from <= order_date <= date_to and order["currency"] == currency:
                order_ids_by_date[order_date].add(int(order["id"]))
        daily = frame.groupby("summary_date", as_index=False)[
            ["orders_count", "items_count", "gross_cents", "discount_cents", "tax_cents"]
        ].sum()
        computed_at = datetime.now(timezone.utc)
        for row in daily.to_dict(orient="records"):
            summary_date = row["summary_date"]
            values = {key: int(row[key]) for key in ("orders_count", "items_count", "gross_cents", "discount_cents", "tax_cents")}
            values["orders_count"] = len(order_ids_by_date[summary_date])
            summary = {
                "summary_date": summary_date, "currency": currency, **values,
                "net_cents": values["gross_cents"] - values["discount_cents"] - values["tax_cents"],
                "computed_at": computed_at,
            }
            if recompute or summary_date not in existing_by_date:
                _SUMMARIES[(tenant_id, summary_date, currency)] = summary
                summaries.append(summary)
                written += 1
    return summaries, written


def read_daily(tenant_id: int, date_from: date, date_to: date, currency: str) -> list[dict[str, Any]]:
    return sorted(
        [row for (stored_tenant, stored_date, stored_currency), row in _SUMMARIES.items()
         if stored_tenant == tenant_id and stored_currency == currency and date_from <= stored_date <= date_to],
        key=lambda row: row["summary_date"],
    )
