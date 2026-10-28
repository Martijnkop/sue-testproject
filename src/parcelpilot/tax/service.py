from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any


def tax_for_line(
    amount_cents: int,
    rules: Iterable[Mapping[str, Any]],
    *,
    country_code: str | None,
    region: str | None,
    category_id: int | None,
    as_of: date,
) -> int:
    if country_code is None:
        return 0

    country = country_code.upper()
    region_key = region.casefold() if region is not None else None
    matches: list[Mapping[str, Any]] = []
    for rule in rules:
        if rule["country_code"].upper() != country:
            continue
        if rule["region"] is not None and (
            region_key is None or rule["region"].casefold() != region_key
        ):
            continue
        if rule["category_id"] is not None and rule["category_id"] != category_id:
            continue
        if rule["valid_from"] > as_of:
            continue
        if rule["valid_to"] is not None and rule["valid_to"] < as_of:
            continue
        matches.append(rule)

    if not matches:
        return 0

    selected = max(
        matches,
        key=lambda rule: (
            rule["priority"],
            rule["category_id"] is not None,
            rule["region"] is not None,
            -int(rule.get("id", 0)),
        ),
    )
    threshold = selected["threshold_cents"] or 0
    taxable_cents = max(0, amount_cents - threshold)
    return (taxable_cents * selected["rate_bps"] + 5000) // 10000
