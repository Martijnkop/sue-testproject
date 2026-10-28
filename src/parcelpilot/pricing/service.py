from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from parcelpilot.pricing.cache import (
    DiscountSnapshot,
    begin_quote_call,
    compute_quote,
    quote_was_cached,
)
from parcelpilot.tax.service import tax_for_line


def quote_line(
    sku: str,
    quantity: int,
    customer_id: int | None,
    currency: str,
    requested_at: datetime,
    tenant_id: int,
    product_id: int,
    unit_price_cents: int,
    discounts: tuple[DiscountSnapshot, ...],
) -> tuple[int, int, bool]:
    begin_quote_call()
    discount_cents, total_cents = compute_quote(
        sku,
        quantity,
        customer_id,
        currency,
        requested_at,
        tenant_id,
        product_id,
        unit_price_cents,
        discounts,
    )
    return discount_cents, total_cents, quote_was_cached()


def price_line(
    unit_price_cents: int,
    quantity: int,
    discounts: Iterable[Mapping[str, Any]],
    *,
    requested_at: datetime,
    shipping_cents: int = 0,
    tax_rules: Iterable[Mapping[str, Any]] = (),
    country_code: str | None = None,
    region: str | None = None,
    category_id: int | None = None,
    applied_codes: set[str] | None = None,
) -> dict[str, int]:
    subtotal_cents = unit_price_cents * quantity
    remaining_cents = subtotal_cents
    remaining_shipping_cents = shipping_cents
    discount_cents = 0
    applied_groups: set[str] = set()

    for discount in discounts:
        if not discount["is_active"]:
            continue
        if discount["valid_from"] is not None and requested_at < discount["valid_from"]:
            continue
        if discount["valid_to"] is not None and requested_at >= discount["valid_to"]:
            continue
        if subtotal_cents < discount["min_subtotal_cents"]:
            continue
        if discount["max_uses"] is not None and discount["used_count"] >= discount["max_uses"]:
            continue

        stack_group = discount["stack_group"]
        if stack_group is not None and stack_group in applied_groups:
            continue

        kind = discount["kind"]
        if kind == "shipping":
            amount_cents = min(max(discount["value"], 0), remaining_shipping_cents)
            if amount_cents == 0:
                continue
            remaining_shipping_cents -= amount_cents
            discount_cents += amount_cents
            if applied_codes is not None and discount.get("code"):
                applied_codes.add(str(discount["code"]))
            if stack_group is not None:
                applied_groups.add(stack_group)
            continue
        elif kind == "percent":
            amount_cents = (remaining_cents * discount["value"] + 5000) // 10000
        elif kind == "fixed":
            amount_cents = discount["value"]
        else:
            continue
        amount_cents = min(max(amount_cents, 0), remaining_cents)
        if amount_cents == 0:
            continue
        remaining_cents -= amount_cents
        discount_cents += amount_cents
        if applied_codes is not None and discount.get("code"):
            applied_codes.add(str(discount["code"]))
        if stack_group is not None:
            applied_groups.add(stack_group)

    tax_cents = tax_for_line(
        remaining_cents,
        tax_rules,
        country_code=country_code,
        region=region,
        category_id=category_id,
        as_of=requested_at.date(),
    )
    return {
        "unit_price_cents": unit_price_cents,
        "discount_cents": discount_cents,
        "tax_cents": tax_cents,
        "total_cents": remaining_cents + tax_cents + remaining_shipping_cents,
    }
