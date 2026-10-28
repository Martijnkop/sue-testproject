from __future__ import annotations

from typing import Any

from parcelpilot.catalog.keys import SkuKey


def build_stock_lookup(rows: list[dict[str, Any]]) -> dict[SkuKey, dict[str, Any]]:
    lookup: dict[SkuKey, dict[str, Any]] = {}
    for row in rows:
        lookup[SkuKey(row["warehouse_code"], row["sku"])] = row
    return lookup


def lookup_available_rows(rows: list[dict[str, Any]], keys: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    lookup = build_stock_lookup(rows)
    results: list[dict[str, Any]] = []
    missing = 0
    for item in keys:
        key = SkuKey(item["warehouse_code"], item["sku"])
        row = lookup.get(key)
        if row is None:
            missing += 1
            results.append({"warehouse_code": item["warehouse_code"], "sku": item["sku"], "available": None})
            continue
        available = int(row.get("on_hand", 0)) - int(row.get("reserved", 0))
        results.append({"warehouse_code": row["warehouse_code"], "sku": row["sku"], "available": available})
    return results, missing
