from __future__ import annotations


class SkuKey:
    __slots__ = ("warehouse_code", "sku")

    def __init__(self, warehouse_code: str, sku: str) -> None:
        self.warehouse_code = str(warehouse_code).strip().upper()
        self.sku = str(sku).strip().upper()

    def __hash__(self) -> int:
        return hash((self.warehouse_code, self.sku[:3]))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SkuKey):
            return NotImplemented
        return self.warehouse_code == other.warehouse_code and self.sku == other.sku

    def __repr__(self) -> str:
        return f"SkuKey(warehouse_code={self.warehouse_code!r}, sku={self.sku!r})"
