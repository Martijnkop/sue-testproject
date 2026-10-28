from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def to_cents(value: str) -> int:
    try:
        return int((Decimal(value.replace(",", "").strip()) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid unit_price") from exc


def clean_postal(value: str | None) -> str | None:
    return value.strip() or None if value is not None else None


def title_city(value: str | None) -> str | None:
    return value.strip().title() or None if value is not None else None


def geocode_stub(postal: str | None, country: str | None) -> dict[str, str | None]:
    return {"postal_code": postal, "country": country.upper() if country else None}
