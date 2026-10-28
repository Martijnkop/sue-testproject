from __future__ import annotations

from datetime import date
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from parcelpilot.analytics import daily, tax
from parcelpilot.core.security import get_current_user, require_roles

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("")
def analytics_root() -> dict[str, str]:
    return {"status": "ok"}


class DailyComputeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date_from: date
    date_to: date
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    recompute: bool = False

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        normalized = value.upper()
        if not normalized.isalpha():
            raise ValueError("currency must contain only letters")
        return normalized


class TaxLine(BaseModel):
    model_config = ConfigDict(extra="ignore")

    amount_cents: int = Field(ge=0)
    category_id: int | None = Field(default=None, gt=0)


class TaxEstimateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    country_code: str = Field(min_length=2, max_length=2)
    region: str | None = None
    lines: list[TaxLine] = Field(max_length=100000)

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, value: str) -> str:
        normalized = value.upper()
        if not normalized.isalpha():
            raise ValueError("country_code must contain only letters")
        return normalized


@router.post("/daily/compute")
def compute_daily(payload: DailyComputeRequest, user: dict[str, Any] = Depends(require_roles("admin", "analyst"))) -> dict[str, Any]:
    if payload.date_from > payload.date_to:
        raise HTTPException(status_code=422, detail={"code": "invalid_date_range", "message": "date_from must not be after date_to"})
    days = (payload.date_to - payload.date_from).days + 1
    if days > 366:
        raise HTTPException(status_code=422, detail={"code": "date_range_too_large", "message": "Daily analytics ranges may not exceed 366 days"})
    started = perf_counter()
    _, written = daily.compute_daily(int(user["tenant_id"]), payload.date_from, payload.date_to, payload.currency.upper(), payload.recompute)
    return {"days_computed": days, "summaries_written": written, "duration_ms": round((perf_counter() - started) * 1000)}


@router.get("/daily")
def get_daily(
    date_from: date,
    date_to: date,
    currency: str = Query(default="EUR", min_length=3, max_length=3),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if date_from > date_to:
        raise HTTPException(status_code=422, detail={"code": "invalid_date_range", "message": "date_from must not be after date_to"})
    return {"items": daily.read_daily(int(user["tenant_id"]), date_from, date_to, currency.upper())}


@router.post("/tax/estimate")
def estimate_tax(payload: TaxEstimateRequest, user: dict[str, Any] = Depends(require_roles("admin", "ops", "analyst", "viewer"))) -> dict[str, Any]:
    return tax.estimate(
        int(user["tenant_id"]), payload.country_code.upper(), payload.region,
        [line.model_dump() for line in payload.lines],
    )
