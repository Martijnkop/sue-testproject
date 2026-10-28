from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from parcelpilot.fraud.lookup import matching_entries

logger = logging.getLogger(__name__)

_ORDER_SNAPSHOTS: dict[tuple[int, int], dict[str, Any]] = {}
_CHECK_SEQUENCE = 0

_MATCH_WEIGHTS = {
    "email": 40,
    "ip": 30,
    "name": 15,
    "phone": 20,
    "address": 20,
}


def register_order_snapshot(tenant_id: int, order_id: int, payload: Mapping[str, Any]) -> None:
    _ORDER_SNAPSHOTS[(tenant_id, order_id)] = dict(payload)


def get_order_snapshot(tenant_id: int, order_id: int) -> dict[str, Any] | None:
    snapshot = _ORDER_SNAPSHOTS.get((tenant_id, order_id))
    return dict(snapshot) if snapshot is not None else None


def _address_value(value: Any) -> str | None:
    if isinstance(value, Mapping):
        parts = [
            str(value.get(field, ""))
            for field in ("line1", "line2", "city", "region", "postal_code", "country_code")
        ]
        result = " ".join(part for part in parts if part.strip())
        return result or None
    if isinstance(value, str):
        return value
    return None


def screen_order(payload: Mapping[str, Any], tenant_id: int, order_id: int | None = None) -> dict[str, Any]:
    global _CHECK_SEQUENCE
    values = {
        "email": payload.get("email"),
        "ip": payload.get("ip_address", payload.get("client_ip")),
        "name": payload.get("full_name"),
        "phone": payload.get("phone"),
        "address": _address_value(payload.get("shipping_address")),
    }
    matches: list[dict[str, Any]] = []
    score = 0
    for entry_type, value in values.items():
        if not isinstance(value, str) or not value.strip():
            continue
        for entry in matching_entries(entry_type, value, tenant_id):
            score += _MATCH_WEIGHTS[entry_type]
            matches.append(
                {
                    "entry_id": entry["id"],
                    "entry_type": entry_type,
                    "value": entry["value"],
                    "reason": entry["reason"],
                }
            )

    score = min(score, 100)
    decision = "block" if score >= 80 else "review" if score >= 50 else "allow"
    logger.debug(f"fraud screening matches: {matches}")
    _CHECK_SEQUENCE += 1
    return {
        "check_id": _CHECK_SEQUENCE,
        "order_id": order_id,
        "decision": decision,
        "score": float(score),
        "matches": matches,
    }
