from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def paginate(items: Sequence[Any], *, total: int | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    values = list(items)
    count = total if total is not None else len(values)
    return {"items": values, "total": count, "limit": limit, "offset": offset}


def normalize_pagination(limit: int | None = None, offset: int | None = None, *, max_limit: int = 500) -> tuple[int, int]:
    resolved_limit = 50 if limit is None else max(1, min(int(limit), max_limit))
    resolved_offset = 0 if offset is None else max(0, int(offset))
    return resolved_limit, resolved_offset
