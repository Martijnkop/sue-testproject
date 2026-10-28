from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

import numpy as np

from parcelpilot.orders import service as order_service


def rules_for(tenant_id: int, country_code: str, region: str | None, category_id: int | None, as_of: date) -> Mapping[str, Any] | None:
    rules = order_service._TAX_RULES.get(tenant_id, order_service._DEFAULT_TAX_RULES)
    country = country_code.upper()
    region_key = region.casefold() if region else None
    matching = [
        rule for rule in rules
        if rule["country_code"].upper() == country
        and (rule["region"] is None or (region_key is not None and rule["region"].casefold() == region_key))
        and (rule["category_id"] is None or rule["category_id"] == category_id)
        and rule["valid_from"] <= as_of
        and (rule["valid_to"] is None or rule["valid_to"] >= as_of)
    ]
    if not matching:
        return None
    return max(matching, key=lambda rule: (
        rule["priority"], rule["category_id"] is not None, rule["region"] is not None, -int(rule.get("id", 0))
    ))


def compute_tax(amount_cents: int, rule: Mapping[str, Any] | None) -> tuple[int, int, int | None]:
    if rule is None:
        return 0, 0, None
    taxable = max(0, int(amount_cents) - int(rule.get("threshold_cents") or 0))
    tax = (taxable * int(rule["rate_bps"]) + 5000) // 10000
    return tax, int(rule["rate_bps"]), int(rule["id"]) if rule.get("id") is not None else None


def estimate(tenant_id: int, country_code: str, region: str | None, lines: Sequence[dict[str, Any]]) -> dict[str, Any]:
    as_of = date.today()
    line_rules = [rules_for(tenant_id, country_code, region, line.get("category_id"), as_of) for line in lines]
    if lines:
        tax_vec = np.vectorize(lambda amt, rule: compute_tax(int(amt), rule), otypes=[object])
        computed = tax_vec(
            np.asarray([line["amount_cents"] for line in lines], dtype=np.int64),
            np.asarray(line_rules, dtype=object),
        )
        results = list(computed)
    else:
        results = []
    rendered = [
        {"index": index, "tax_cents": int(result[0]), "rate_bps": int(result[1]), "rule_id": result[2]}
        for index, result in enumerate(results)
    ]
    return {"total_tax_cents": sum(line["tax_cents"] for line in rendered), "lines": rendered}
