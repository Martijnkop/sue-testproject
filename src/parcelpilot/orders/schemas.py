from __future__ import annotations

import ipaddress
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


class OrderItemInput(BaseModel):
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


class OrderAddressInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    postal_code: str = Field(min_length=1, max_length=20)
    country_code: str = Field(default="DE", min_length=2, max_length=2)

    @field_validator("line1", "line2", "city", "region", "postal_code")
    @classmethod
    def strip_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized and info.field_name in {"line1", "city", "postal_code"}:
            raise ValueError(f"{info.field_name} must not be blank")
        return normalized or None

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        country_code = value.strip().upper()
        if len(country_code) != 2 or not country_code.isalpha():
            raise ValueError("country_code must be a two-letter code")
        return country_code


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    customer_id: int = Field(gt=0)
    external_ref: str | None = Field(default=None, max_length=100)
    currency: str = Field(min_length=3, max_length=3)
    client_ip: str | None = Field(default=None, max_length=45)
    items: list[OrderItemInput] = Field(min_length=1)
    shipping_address_id: int | None = Field(default=None, gt=0)
    shipping_address: OrderAddressInput | None = None
    discount_codes: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("external_ref", "client_ip", "notes")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("client_ip")
    @classmethod
    def normalize_client_ip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError as exc:
            raise ValueError("client_ip must be a valid IP address") from exc

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        currency = value.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        return currency

    @field_validator("discount_codes")
    @classmethod
    def normalize_discount_codes(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().upper() for value in values]
        if any(not value for value in normalized):
            raise ValueError("discount codes must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_address_and_skus(self) -> OrderCreate:
        if (self.shipping_address_id is None) == (self.shipping_address is None):
            raise ValueError("Provide exactly one shipping address source")
        skus = [item.sku for item in self.items]
        if len(skus) != len(set(skus)):
            raise ValueError("Order items must not contain duplicate SKUs")
        return self


class OrderStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal[
        "pending",
        "fraud_review",
        "confirmed",
        "picking",
        "shipped",
        "delivered",
        "cancelled",
    ]
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("reason must not be blank")
        return reason


def render_order(order: dict[str, Any]) -> str:
    items = order.get("items", [])
    return (
        f"order={order.get('id')} status={order.get('status')} "
        f"items={[(item.get('sku'), item.get('quantity')) for item in items]}"
    )


def copy_payload(value: dict[str, Any]) -> dict[str, Any]:
    return dict(value)


def deepcopy_payload(value: dict[str, Any]) -> dict[str, Any]:
    import copy

    return copy.deepcopy(value)
