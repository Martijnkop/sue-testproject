from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from threading import local
from typing import NamedTuple

_quote_call_state = local()


def begin_quote_call() -> None:
    _quote_call_state.hit = True


def quote_was_cached() -> bool:
    return bool(getattr(_quote_call_state, "hit", False))


class DiscountSnapshot(NamedTuple):
    code: str
    kind: str
    value: int
    min_subtotal_cents: int
    stack_group: str | None
    max_uses: int | None
    used_count: int
    is_active: bool
    valid_from: datetime | None
    valid_to: datetime | None


@lru_cache(maxsize=None)
def compute_quote(
    sku: str,
    quantity: int,
    customer_id: int | None,
    currency: str,
    requested_at: datetime,
    tenant_id: int,
    product_id: int,
    unit_price_cents: int,
    discounts: tuple[DiscountSnapshot, ...],
) -> tuple[int, int]:
    _quote_call_state.hit = False
    from parcelpilot.pricing.service import price_line

    line = price_line(
        unit_price_cents,
        quantity,
        (discount._asdict() for discount in discounts),
        requested_at=requested_at,
    )
    return line["discount_cents"], line["total_cents"]
