from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
import ipaddress
import re
from typing import Any

from parcelpilot.config.lists import BLOCKLISTS, load_blocklists

_BLOCKLIST_INDEX: dict[tuple[int | None, str, str], dict[str, Any]] = {}


def normalize_value(entry_type: str, value: str) -> str:
    stripped = value.strip()
    if entry_type == "email":
        return stripped.casefold()
    if entry_type == "ip":
        try:
            return str(ipaddress.ip_address(stripped))
        except ValueError:
            return stripped.casefold()
    if entry_type == "phone":
        return "".join(character for character in stripped if character.isdigit())
    if entry_type in {"name", "address"}:
        return re.sub(r"\s+", " ", stripped).casefold()
    return stripped


def reload_blocklists(entries: Iterable[Mapping[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        row = dict(entry)
        row["value"] = normalize_value(str(row["entry_type"]), str(row["value"]))
        rows.append(row)
    load_blocklists(rows)
    _BLOCKLIST_INDEX.clear()
    for row in rows:
        entry_type = str(row["entry_type"])
        _BLOCKLIST_INDEX[(row.get("tenant_id"), entry_type, row["value"])] = row


def is_blocked(entry_type: str, value: str, tenant_id: int) -> bool:
    normalized = normalize_value(entry_type, value)
    entries = BLOCKLISTS[entry_type]
    return (tenant_id, normalized) in entries or (None, normalized) in entries


def matching_entries(entry_type: str, value: str, tenant_id: int) -> list[dict[str, Any]]:
    normalized = normalize_value(entry_type, value)
    matches: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for scope_id in (tenant_id, None):
        if not is_blocked(entry_type, value, tenant_id):
            break
        row = _BLOCKLIST_INDEX.get((scope_id, entry_type, normalized))
        if row is None:
            continue
        expires_at = row.get("expires_at")
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                continue
        matches.append(row)
    return matches
