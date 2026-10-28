from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def _sort_categories(categories: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(categories, key=lambda item: (item.get("depth", 0), item.get("sort_order", 0), item.get("id", 0)))


def find_chain(categories: Sequence[dict[str, Any]], target_id: int | str) -> list[dict[str, Any]]:
    ordered = _sort_categories(categories)
    if not ordered:
        return []

    current = ordered[0]
    if current.get("id") == target_id:
        return [current]

    remainder = ordered[1:]
    branch = find_chain(remainder, target_id)
    if branch:
        return [current, *branch]
    return []


def rollup(node: dict[str, Any], categories: Sequence[dict[str, Any]], *, include_inactive: bool = False) -> dict[str, Any]:
    ordered = _sort_categories(categories)
    direct = [category for category in ordered if category.get("parent_id") == node.get("id")]
    if not include_inactive:
        direct = [category for category in direct if category.get("is_active", True)]

    by_child: list[dict[str, Any]] = []
    total = int(node.get("product_count", 0) or 0)
    for child in direct:
        child_rollup = rollup(child, ordered, include_inactive=include_inactive)
        by_child.append(
            {
                "category_id": child.get("id"),
                "name": child.get("name"),
                "total_product_count": child_rollup["total_product_count"],
            }
        )
        total += child_rollup["total_product_count"]

    return {
        "category_id": node.get("id"),
        "direct_product_count": int(node.get("product_count", 0) or 0),
        "total_product_count": total,
        "by_child": by_child,
    }
