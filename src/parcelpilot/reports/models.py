from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parcelpilot.reports.keys import expensive_key


@dataclass
class Report:
    run_id: int
    tenant_id: int
    params: dict[str, Any]
    _rows: list[dict[str, Any]]
    sort_by: str = "revenue_cents"
    order: str = "desc"

    @property
    def sorted_rows(self) -> list[dict[str, Any]]:
        reverse = self.order == "desc"
        if self.sort_by == "label":
            return sorted(self._rows, key=expensive_key, reverse=reverse)
        return sorted(self._rows, key=lambda row: row[self.sort_by], reverse=reverse)

    def configure(self, sort_by: str, order: str) -> None:
        self.sort_by = sort_by
        self.order = order
