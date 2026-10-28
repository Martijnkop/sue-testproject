from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from parcelpilot.fraud.lookup import normalize_value, reload_blocklists

_ENTRIES: dict[int, dict[str, Any]] = {}
_ENTRY_SEQUENCE = 0


def list_entries(tenant_id: int, *, include_expired: bool) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    result: list[dict[str, Any]] = []
    for entry in _ENTRIES.values():
        if entry["tenant_id"] not in (tenant_id, None):
            continue
        expires_at = entry["expires_at"]
        if expires_at is not None:
            normalized_expiry = expires_at
            if normalized_expiry.tzinfo is None:
                normalized_expiry = normalized_expiry.replace(tzinfo=timezone.utc)
            if normalized_expiry <= now and not include_expired:
                continue
        result.append(entry)
    return result


def add_entries(tenant_id: int | None, entries: list[dict[str, Any]]) -> tuple[int, int]:
    global _ENTRY_SEQUENCE
    existing = {
        (entry["tenant_id"], entry["entry_type"], entry["value"])
        for entry in _ENTRIES.values()
    }
    created = 0
    skipped = 0
    now = datetime.now(timezone.utc)
    for payload in entries:
        entry_type = payload["entry_type"]
        value = normalize_value(entry_type, payload["value"])
        identity = (tenant_id, entry_type, value)
        if identity in existing:
            skipped += 1
            continue
        _ENTRY_SEQUENCE += 1
        expires_at = payload.get("expires_at")
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        _ENTRIES[_ENTRY_SEQUENCE] = {
            "id": _ENTRY_SEQUENCE,
            "tenant_id": tenant_id,
            "entry_type": entry_type,
            "value": value,
            "reason": payload["reason"],
            "source": "manual",
            "expires_at": expires_at,
            "created_at": now,
        }
        existing.add(identity)
        created += 1
    reload_blocklists(_ENTRIES.values())
    return created, skipped


def remove_entry(tenant_id: int, entry_id: int) -> bool:
    entry = _ENTRIES.get(entry_id)
    if entry is None or entry["tenant_id"] != tenant_id:
        return False
    del _ENTRIES[entry_id]
    reload_blocklists(_ENTRIES.values())
    return True


def serialize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    expires_at = entry["expires_at"]
    created_at = entry["created_at"]
    return {
        "id": entry["id"],
        "entry_type": entry["entry_type"],
        "value": entry["value"],
        "reason": entry["reason"],
        "source": entry["source"],
        "scope": "global" if entry["tenant_id"] is None else "tenant",
        "expires_at": expires_at.isoformat().replace("+00:00", "Z") if expires_at else None,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
    }
