from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_BUNDLES: dict[tuple[int, int], dict[str, Any]] = {}
_BUNDLE_SEQUENCE = 0


def create_bundle(
    tenant_id: int,
    name: str,
    items: list[dict[str, Any]],
    discount_ids: list[int],
    products: dict[str, dict[str, Any]],
    discounts: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    global _BUNDLE_SEQUENCE
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        sku = str(item["sku"]).strip().upper()
        product = products.get(sku)
        if product is None or not product.get("is_active", True):
            raise ValueError(f"Product {sku!r} is not available")
        normalized_items.append({"sku": sku, "quantity": int(item["quantity"])})

    if len(discount_ids) != len(set(discount_ids)):
        raise ValueError("discount_ids must not contain duplicates")
    if any(discount_id not in discounts for discount_id in discount_ids):
        raise ValueError("A discount id is not available")

    _BUNDLE_SEQUENCE += 1
    bundle = {
        "id": _BUNDLE_SEQUENCE,
        "name": name,
        "is_active": True,
        "items": normalized_items,
        "discount_ids": list(discount_ids),
    }
    _BUNDLES[(tenant_id, _BUNDLE_SEQUENCE)] = bundle
    return bundle


def get_bundle(tenant_id: int, bundle_id: int) -> dict[str, Any] | None:
    bundle = _BUNDLES.get((tenant_id, bundle_id))
    return dict(bundle) if bundle is not None else None


def bundle_subtotal(
    items: list[dict[str, Any]],
    products: dict[str, dict[str, Any]],
) -> int:
    subtotal_cents = 0
    for item in items:
        sku = str(item["sku"]).strip().upper()
        product = products.get(sku)
        if product is None or not product.get("is_active", True):
            raise ValueError(f"Product {sku!r} is not available")
        subtotal_cents += int(product.get("base_price_cents", 0)) * int(item["quantity"])
    return subtotal_cents


def best_combination(
    subtotal_cents: int,
    candidates: list[dict[str, Any]],
    max_stacked: int,
    *,
    requested_at: datetime | None = None,
) -> dict[str, Any]:
    if requested_at is None:
        requested_at = datetime.now(timezone.utc)
    if requested_at.tzinfo is None:
        requested_at = requested_at.replace(tzinfo=timezone.utc)
    candidates = sorted(candidates, key=lambda discount: int(discount["id"]))
    best_ids: tuple[int, ...] = ()
    best_savings: tuple[int, ...] = ()
    best_total = -1
    combinations_evaluated = 0

    def best(
        index: int,
        chosen_ids: tuple[int, ...],
        chosen_savings: tuple[int, ...],
        remaining_cents: int,
        used_groups: frozenset[str],
        valid: bool,
    ) -> None:
        nonlocal best_ids, best_savings, best_total, combinations_evaluated
        if index == len(candidates):
            combinations_evaluated += 1
            if not valid:
                return
            total_savings = subtotal_cents - remaining_cents
            if total_savings > best_total or (total_savings == best_total and chosen_ids < best_ids):
                best_total = total_savings
                best_ids = chosen_ids
                best_savings = chosen_savings
            return

        candidate = candidates[index]
        best(
            index + 1,
            chosen_ids,
            chosen_savings,
            remaining_cents,
            used_groups,
            valid,
        )

        stack_group = candidate["stack_group"]
        valid_from = candidate["valid_from"]
        valid_to = candidate["valid_to"]
        available = (
            candidate["is_active"]
            and subtotal_cents >= candidate["min_subtotal_cents"]
            and (candidate["max_uses"] is None or candidate["used_count"] < candidate["max_uses"])
            and (valid_from is None or requested_at >= valid_from)
            and (valid_to is None or requested_at < valid_to)
            and candidate["kind"] in {"percent", "fixed"}
        )
        within_limit = len(chosen_ids) < max_stacked
        group_available = stack_group is None or stack_group not in used_groups

        kind = candidate["kind"]
        if kind == "percent":
            savings = (remaining_cents * int(candidate["value"]) + 5000) // 10000
        elif kind == "fixed":
            savings = int(candidate["value"])
        else:
            savings = 0
        savings = min(max(savings, 0), remaining_cents)
        can_apply = available and within_limit and group_available and savings > 0
        best(
            index + 1,
            chosen_ids + (int(candidate["id"]),),
            chosen_savings + (savings,),
            remaining_cents - savings if can_apply else remaining_cents,
            used_groups | ({stack_group} if stack_group is not None else set()) if can_apply else used_groups,
            valid and can_apply,
        )

    best(0, (), (), subtotal_cents, frozenset(), True)
    by_id = {int(candidate["id"]): candidate for candidate in candidates}
    best_rows = [
        {
            "discount_id": discount_id,
            "code": by_id[discount_id]["code"],
            "savings_cents": savings_cents,
        }
        for discount_id, savings_cents in zip(best_ids, best_savings)
    ]
    return {
        "subtotal_cents": subtotal_cents,
        "best_combination": best_rows,
        "total_savings_cents": max(best_total, 0),
        "final_total_cents": subtotal_cents - max(best_total, 0),
        "combinations_evaluated": combinations_evaluated,
    }
