from __future__ import annotations

import unicodedata
from typing import Any


def expensive_key(row: dict[str, Any]) -> str:
    return unicodedata.normalize("NFKD", str(row["label"])).casefold()
