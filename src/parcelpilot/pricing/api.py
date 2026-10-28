from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from parcelpilot.catalog.api import _PRODUCTS
from parcelpilot.core.pagination import normalize_pagination
from parcelpilot.core.security import require_roles
from parcelpilot.pricing.bundles import best_combination, bundle_subtotal, create_bundle, get_bundle
from parcelpilot.pricing.cache import DiscountSnapshot
from parcelpilot.pricing.service import quote_line

router = APIRouter(prefix="/pricing", tags=["pricing"])

_DISCOUNTS: dict[int, dict[str, dict[str, Any]]] = {}
_QUOTES: dict[tuple[int, int], dict[str, Any]] = {}
_DISCOUNT_SEQUENCE = 0
_QUOTE_SEQUENCE = 0


class DiscountInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str = Field(min_length=1, max_length=50)
    kind: Literal["percent", "fixed", "shipping"]
    value: int = Field(ge=0)
    min_subtotal_cents: int = Field(default=0, ge=0)
    stack_group: str | None = Field(default=None, max_length=50)
    max_uses: int | None = Field(default=None, ge=0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        code = value.strip().upper()
        if not code:
            raise ValueError("code must not be blank")
        return code

    @field_validator("valid_from", "valid_to")
    @classmethod
    def normalize_validity_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_validity_window(self) -> DiscountInput:
        if self.valid_from is not None and self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from")
        return self


class DiscountsCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    discounts: list[DiscountInput] = Field(default_factory=list)


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(gt=0)
    customer_id: int | None = None
    currency: str = Field(min_length=3, max_length=3)
    requested_at: datetime | None = None
    discount_codes: list[str] = Field(default_factory=list)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        sku = value.strip().upper()
        if not sku:
            raise ValueError("sku must not be blank")
        return sku

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        currency = value.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        return currency

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class QuoteBatchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requests: list[QuoteRequest] = Field(max_length=1000)


class BundleItemInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(gt=0)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        sku = value.strip().upper()
        if not sku:
            raise ValueError("sku must not be blank")
        return sku


class BundleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200)
    items: list[BundleItemInput] = Field(min_length=1)
    discount_ids: list[int] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("name must not be blank")
        return name

    @model_validator(mode="after")
    def validate_unique_items_and_discounts(self) -> BundleCreateRequest:
        skus = [item.sku for item in self.items]
        if len(skus) != len(set(skus)):
            raise ValueError("items must not contain duplicate SKUs")
        if len(self.discount_ids) != len(set(self.discount_ids)):
            raise ValueError("discount_ids must not contain duplicates")
        if any(discount_id <= 0 for discount_id in self.discount_ids):
            raise ValueError("discount_ids must be positive")
        return self


class BestDiscountRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bundle_id: int | None = Field(default=None, gt=0)
    items: list[BundleItemInput] | None = Field(default=None, min_length=1)
    candidate_discount_ids: list[int] | None = None
    max_stacked: int = Field(default=6, ge=0)

    @model_validator(mode="after")
    def validate_source(self) -> BestDiscountRequest:
        if (self.bundle_id is None) == (self.items is None):
            raise ValueError("Provide exactly one of bundle_id or items")
        if self.items is not None and self.candidate_discount_ids is None:
            raise ValueError("candidate_discount_ids is required when items are provided")
        if self.candidate_discount_ids is not None and len(self.candidate_discount_ids) != len(
            set(self.candidate_discount_ids)
        ):
            raise ValueError("candidate_discount_ids must not contain duplicates")
        if self.items is not None:
            skus = [item.sku for item in self.items]
            if len(skus) != len(set(skus)):
                raise ValueError("items must not contain duplicate SKUs")
        if self.candidate_discount_ids is not None and any(
            discount_id <= 0 for discount_id in self.candidate_discount_ids
        ):
            raise ValueError("candidate_discount_ids must be positive")
        return self


@router.get("")
def pricing_root() -> dict[str, str]:
    return {"status": "ok"}


def _tenant_id(user: dict[str, Any]) -> int:
    return int(user["tenant_id"])


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="auto").replace("+00:00", "Z")


def _serialize_discount(discount: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": discount["id"],
        "code": discount["code"],
        "kind": discount["kind"],
        "value": discount["value"],
        "min_subtotal_cents": discount["min_subtotal_cents"],
        "stack_group": discount["stack_group"],
        "max_uses": discount["max_uses"],
        "used_count": discount["used_count"],
        "is_active": discount["is_active"],
        "valid_from": _format_timestamp(discount["valid_from"]) if discount["valid_from"] else None,
        "valid_to": _format_timestamp(discount["valid_to"]) if discount["valid_to"] else None,
    }


def _resolve_discounts(tenant_id: int, codes: list[str]) -> tuple[DiscountSnapshot, ...]:
    tenant_discounts = _DISCOUNTS.get(tenant_id, {})
    snapshots: list[DiscountSnapshot] = []
    seen: set[str] = set()
    for raw_code in codes:
        code = raw_code.strip().upper()
        if code in seen:
            continue
        seen.add(code)
        discount = tenant_discounts.get(code)
        if discount is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "discount_not_found", "message": f"Discount code {code!r} is not available"},
            )
        snapshots.append(
            DiscountSnapshot(
                code=discount["code"],
                kind=discount["kind"],
                value=discount["value"],
                min_subtotal_cents=discount["min_subtotal_cents"],
                stack_group=discount["stack_group"],
                max_uses=discount["max_uses"],
                used_count=discount["used_count"],
                is_active=discount["is_active"],
                valid_from=discount["valid_from"],
                valid_to=discount["valid_to"],
            )
        )
    return tuple(snapshots)


def _create_quote(payload: QuoteRequest, tenant_id: int) -> dict[str, Any]:
    sku = payload.sku.strip().upper()
    product = _PRODUCTS.get(sku)
    if product is None or not product.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "sku_not_found", "message": "Product not found"},
        )

    currency = payload.currency.upper()
    if currency != str(product.get("currency", "EUR")).upper():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "currency_mismatch", "message": "Quote currency must match the product currency"},
        )

    requested_at = payload.requested_at or datetime.now(timezone.utc)
    discounts = _resolve_discounts(tenant_id, payload.discount_codes)
    discount_cents, total_cents, cache_hit = quote_line(
        sku,
        payload.quantity,
        payload.customer_id,
        currency,
        requested_at,
        tenant_id,
        int(product["id"]),
        int(product.get("base_price_cents", 0)),
        discounts,
    )

    global _QUOTE_SEQUENCE
    _QUOTE_SEQUENCE += 1
    expires_at = requested_at + timedelta(minutes=30)
    quote = {
        "quote_id": _QUOTE_SEQUENCE,
        "sku": sku,
        "quantity": payload.quantity,
        "currency": currency,
        "unit_price_cents": int(product.get("base_price_cents", 0)),
        "discount_cents": discount_cents,
        "total_cents": total_cents,
        "requested_at": _format_timestamp(requested_at),
        "expires_at": _format_timestamp(expires_at),
        "cache_hit": cache_hit,
    }
    _QUOTES[(tenant_id, _QUOTE_SEQUENCE)] = quote
    return quote


@router.post("/discounts", status_code=status.HTTP_201_CREATED)
def create_discounts(
    payload: DiscountsCreateRequest,
    user: dict[str, Any] = Depends(require_roles("admin")),
) -> dict[str, int]:
    tenant_id = _tenant_id(user)
    tenant_discounts = _DISCOUNTS.get(tenant_id, {})
    codes = [item.code.strip().upper() for item in payload.discounts]
    if len(codes) != len(set(codes)) or any(code in tenant_discounts for code in codes):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "discount_code_already_exists", "message": "A discount code already exists"},
        )

    tenant_discounts = _DISCOUNTS.setdefault(tenant_id, tenant_discounts)
    global _DISCOUNT_SEQUENCE
    for item, code in zip(payload.discounts, codes):
        _DISCOUNT_SEQUENCE += 1
        tenant_discounts[code] = {
            "id": _DISCOUNT_SEQUENCE,
            "code": code,
            "kind": item.kind,
            "value": item.value,
            "min_subtotal_cents": item.min_subtotal_cents,
            "stack_group": item.stack_group,
            "max_uses": item.max_uses,
            "used_count": 0,
            "is_active": True,
            "valid_from": item.valid_from,
            "valid_to": item.valid_to,
        }
    return {"created": len(payload.discounts)}


@router.get("/discounts")
def list_discounts(
    is_active: bool | None = None,
    valid_on: date | None = None,
    limit: int | None = None,
    offset: int | None = None,
    user: dict[str, Any] = Depends(require_roles("admin", "ops", "analyst", "viewer")),
) -> dict[str, Any]:
    tenant_discounts = _DISCOUNTS.get(_tenant_id(user), {})
    items = list(tenant_discounts.values())
    if is_active is not None:
        items = [item for item in items if item["is_active"] == is_active]
    if valid_on is not None:
        items = [
            item
            for item in items
            if (item["valid_from"] is None or item["valid_from"].date() <= valid_on)
            and (item["valid_to"] is None or item["valid_to"].date() >= valid_on)
        ]
    items.sort(key=lambda item: item["id"])
    resolved_limit, resolved_offset = normalize_pagination(limit, offset)
    page = items[resolved_offset : resolved_offset + resolved_limit]
    return {
        "items": [_serialize_discount(item) for item in page],
        "total": len(items),
        "limit": resolved_limit,
        "offset": resolved_offset,
    }


@router.post("/quotes", status_code=status.HTTP_201_CREATED)
def create_quote(
    payload: QuoteRequest,
    user: dict[str, Any] = Depends(require_roles("admin", "ops", "analyst")),
) -> dict[str, Any]:
    return _create_quote(payload, _tenant_id(user))


@router.post("/quotes/batch", status_code=status.HTTP_201_CREATED)
def create_quote_batch(
    payload: QuoteBatchRequest,
    user: dict[str, Any] = Depends(require_roles("admin", "ops", "analyst")),
) -> dict[str, list[dict[str, Any]]]:
    global _QUOTE_SEQUENCE
    tenant_id = _tenant_id(user)
    previous_sequence = _QUOTE_SEQUENCE
    quotes: list[dict[str, Any]] = []
    try:
        for item in payload.requests:
            quotes.append(_create_quote(item, tenant_id))
    except HTTPException:
        _QUOTE_SEQUENCE = previous_sequence
        for quote in quotes:
            _QUOTES.pop((tenant_id, quote["quote_id"]), None)
        raise
    return {"quotes": quotes}


@router.get("/quotes/{quote_id}")
def get_quote(
    quote_id: int,
    user: dict[str, Any] = Depends(require_roles("admin", "ops", "analyst", "viewer")),
) -> dict[str, Any]:
    quote = _QUOTES.get((_tenant_id(user), quote_id))
    if quote is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "quote_not_found", "message": "Quote not found"},
        )
    return quote


@router.post("/bundles", status_code=status.HTTP_201_CREATED)
def create_pricing_bundle(
    payload: BundleCreateRequest,
    user: dict[str, Any] = Depends(require_roles("admin", "ops")),
) -> dict[str, Any]:
    tenant_id = _tenant_id(user)
    tenant_discounts = {
        int(discount["id"]): discount for discount in _DISCOUNTS.get(tenant_id, {}).values()
    }
    for item in payload.items:
        product = _PRODUCTS.get(item.sku)
        if product is None or not product.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "sku_not_found", "message": f"Product {item.sku!r} is not available"},
            )
    if any(discount_id not in tenant_discounts for discount_id in payload.discount_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "discount_not_found", "message": "A discount id is not available"},
        )
    return create_bundle(
        tenant_id,
        payload.name,
        [item.model_dump() for item in payload.items],
        payload.discount_ids,
        _PRODUCTS,
        tenant_discounts,
    )


@router.post("/bundles/best-discount")
def find_best_bundle_discount(
    payload: BestDiscountRequest,
    user: dict[str, Any] = Depends(require_roles("admin", "ops", "analyst", "viewer")),
) -> dict[str, Any]:
    tenant_id = _tenant_id(user)
    tenant_discounts = {
        int(discount["id"]): discount for discount in _DISCOUNTS.get(tenant_id, {}).values()
    }
    if payload.bundle_id is not None:
        bundle = get_bundle(tenant_id, payload.bundle_id)
        if bundle is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "bundle_not_found", "message": "Bundle not found"},
            )
        items = bundle["items"]
        linked_ids = set(bundle["discount_ids"])
        candidate_ids = (
            bundle["discount_ids"]
            if payload.candidate_discount_ids is None
            else payload.candidate_discount_ids
        )
        if any(discount_id not in linked_ids for discount_id in candidate_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "discount_not_linked",
                    "message": "Candidate discounts must be linked to the bundle",
                },
            )
    else:
        items = [item.model_dump() for item in payload.items or []]
        candidate_ids = payload.candidate_discount_ids or []

    if any(discount_id not in tenant_discounts for discount_id in candidate_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "discount_not_found", "message": "A discount id is not available"},
        )
    try:
        subtotal_cents = bundle_subtotal(items, _PRODUCTS)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "sku_not_found", "message": str(exc)},
        ) from exc
    return best_combination(
        subtotal_cents,
        [tenant_discounts[discount_id] for discount_id in candidate_ids],
        payload.max_stacked,
    )
