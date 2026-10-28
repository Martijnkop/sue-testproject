from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from parcelpilot.core.security import require_roles
from parcelpilot.reports import service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def reports_root() -> dict[str, str]:
    return {"status": "ok"}


class SalesReportRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date_from: date | None = None
    date_to: date | None = None
    group_by: Literal["day", "product", "category", "customer"] = "product"
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    top_n: int | None = Field(default=100, ge=1, le=10000)
    min_revenue_cents: int = Field(default=0, ge=0)


@router.post("/sales", status_code=status.HTTP_201_CREATED)
def create_sales_report(payload: SalesReportRequest, user: dict[str, Any] = Depends(require_roles("admin", "analyst"))) -> dict[str, Any]:
    if payload.date_from and payload.date_to and payload.date_from > payload.date_to:
        raise HTTPException(status_code=422, detail={"code": "invalid_date_range", "message": "date_from must not be after date_to"})
    data = payload.model_dump()
    data["currency"] = payload.currency.upper()
    return service.create_sales_report(int(user["tenant_id"]), int(user["user_id"]), data)


@router.get("/sales/{run_id}/rows")
def get_sales_report_rows(
    run_id: int,
    sort_by: Literal["revenue_cents", "orders_count", "units", "label"] = "revenue_cents",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: dict[str, Any] = Depends(require_roles("admin", "analyst")),
) -> dict[str, Any]:
    report = service.get_report(int(user["tenant_id"]), run_id)
    if report is None:
        raise HTTPException(status_code=404, detail={"code": "report_not_found", "message": "Sales report not found"})
    items, total = service.render_page(report, sort_by=sort_by, order=order, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}
