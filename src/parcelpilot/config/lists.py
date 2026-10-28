from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

BLOCKLISTS: dict[str, list[tuple[int | None, str]]] = {
    "email": [],
    "ip": [],
    "address": [],
    "name": [],
    "phone": [],
}


def load_blocklists(entries: Iterable[Mapping[str, Any]]) -> dict[str, list[tuple[int | None, str]]]:
    now = datetime.now(timezone.utc)
    for values in BLOCKLISTS.values():
        values.clear()

    for entry in entries:
        expires_at = entry.get("expires_at")
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                continue
        entry_type = str(entry["entry_type"])
        value = str(entry["value"])
        BLOCKLISTS[entry_type].append((entry.get("tenant_id"), value))

    return BLOCKLISTS
