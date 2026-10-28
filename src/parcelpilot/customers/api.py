from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from parcelpilot.core.pagination import normalize_pagination

router = APIRouter(prefix="/customers", tags=["customers"])

_CUSTOMERS: dict[int, dict[str, Any]] = {}
_ADDRESS_SEQUENCE = 201


class AddressInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    line1: str
    line2: str | None = None
    city: str
    region: str | None = None
    postal_code: str | None = None
    country_code: str = "DE"
    is_default: bool = False


class CustomerCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str
    full_name: str
    phone: str | None = None
    external_ref: str | None = None
    addresses: list[AddressInput] = Field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _address_coords(city: str) -> tuple[float, float]:
    city_key = city.strip().lower()
    lookup = {
        "leipzig": (51.3397, 12.3731),
        "berlin": (52.52, 13.405),
        "hamburg": (53.5511, 9.9937),
        "munich": (48.1351, 11.582),
    }
    return lookup.get(city_key, (0.0, 0.0))


def _normalize_address(raw: AddressInput) -> dict[str, Any]:
    latitude, longitude = _address_coords(raw.city)
    return {
        "id": 0,
        "line1": raw.line1,
        "line2": raw.line2,
        "city": raw.city,
        "region": raw.region,
        "postal_code": raw.postal_code,
        "country_code": raw.country_code,
        "latitude": latitude,
        "longitude": longitude,
        "is_default": raw.is_default,
        "normalized_at": None,
    }


def _serialize_customer(customer: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": customer["id"],
        "email": customer["email"],
        "full_name": customer["full_name"],
        "phone": customer["phone"],
        "external_ref": customer["external_ref"],
        "addresses": customer["addresses"],
        "created_at": customer["created_at"],
    }


@router.post("")
def create_customer(payload: CustomerCreateRequest) -> dict[str, Any]:
    email = payload.email.strip().lower()
    if any(item["email"] == email for item in _CUSTOMERS.values()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "email_already_exists", "message": "Customer with this email already exists"},
        )

    customer_id = max((customer["id"] for customer in _CUSTOMERS.values()), default=0) + 1
    normalized_addresses: list[dict[str, Any]] = []
    for address in payload.addresses:
        entry = _normalize_address(address)
        global _ADDRESS_SEQUENCE
        entry["id"] = _ADDRESS_SEQUENCE
        _ADDRESS_SEQUENCE += 1
        normalized_addresses.append(entry)

    if normalized_addresses:
        has_default = any(item["is_default"] for item in normalized_addresses)
        if not has_default:
            normalized_addresses[0]["is_default"] = True
    else:
        normalized_addresses = []

    customer = {
        "id": customer_id,
        "email": email,
        "full_name": payload.full_name,
        "phone": payload.phone,
        "external_ref": payload.external_ref,
        "addresses": normalized_addresses,
        "created_at": _now(),
        "order_count": 0,
    }
    _CUSTOMERS[customer_id] = customer
    return _serialize_customer(customer)


@router.get("")
def list_customers(limit: int | None = None, offset: int | None = None) -> dict[str, Any]:
    resolved_limit, resolved_offset = normalize_pagination(limit, offset)
    items = [_serialize_customer(customer) for customer in sorted(_CUSTOMERS.values(), key=lambda item: item["id"])]
    page = items[resolved_offset : resolved_offset + resolved_limit]
    return {"items": page, "total": len(items), "limit": resolved_limit, "offset": resolved_offset}


@router.get("/{customer_id}")
def get_customer(customer_id: int) -> dict[str, Any]:
    customer = _CUSTOMERS.get(customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "customer_not_found", "message": "Customer not found"},
        )
    response = _serialize_customer(customer)
    response["order_count"] = customer.get("order_count", 0)
    return response
