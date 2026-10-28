from __future__ import annotations

import tracemalloc
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from parcelpilot.pricing.cache import DiscountSnapshot, compute_quote
from parcelpilot.pricing.service import price_line
from parcelpilot.tax.service import tax_for_line
from parcelpilot.tests.bench import load_benchmark_threshold
from parcelpilot.tests.oracle_helpers import load_oracle


def _quote_distinct_timestamps(count: int) -> int:
    requested_at = datetime(2026, 10, 10, tzinfo=timezone.utc)
    for microsecond in range(count):
        compute_quote(
            "MUG-WHT",
            3,
            118,
            "EUR",
            requested_at.replace(microsecond=microsecond),
            1,
            5521,
            850,
            (),
        )
    return count


def _discount(
    *,
    valid_from: datetime,
    valid_to: datetime,
    stack_group: str | None = None,
    kind: str = "percent",
    value: int = 1000,
) -> dict[str, Any]:
    return {
        "code": "AUTUMN10",
        "kind": kind,
        "value": value,
        "min_subtotal_cents": 0,
        "stack_group": stack_group,
        "max_uses": None,
        "used_count": 0,
        "is_active": True,
        "valid_from": valid_from,
        "valid_to": valid_to,
    }


@pytest.mark.oracle
def test_price_line_respects_discount_validity_boundary() -> None:
    expected = load_oracle("H7")["validity_window"]
    valid_from = datetime(2026, 10, 1, tzinfo=timezone.utc)
    valid_to = datetime(2026, 11, 1, tzinfo=timezone.utc)
    discount = _discount(valid_from=valid_from, valid_to=valid_to)

    before_expiry = price_line(
        1000,
        2,
        [discount],
        requested_at=valid_to - timedelta(microseconds=1),
    )
    at_expiry = price_line(1000, 2, [discount], requested_at=valid_to)

    assert [
        {
            "discount_cents": before_expiry["discount_cents"],
            "total_cents": before_expiry["total_cents"],
        },
        {
            "discount_cents": at_expiry["discount_cents"],
            "total_cents": at_expiry["total_cents"],
        },
    ] == expected


@pytest.mark.tripwire
def test_quote_cache_misses_for_each_requested_timestamp() -> None:
    compute_quote.cache_clear()

    _quote_distinct_timestamps(12)
    info = compute_quote.cache_info()
    assert info.hits == 0
    assert info.currsize == 12
    compute_quote.cache_clear()


@pytest.mark.bench
def test_quote_cache_benchmark(benchmark: pytest.BenchmarkFixture) -> None:
    threshold = load_benchmark_threshold("H7")
    assert threshold == 3.0

    compute_quote.cache_clear()
    tracemalloc.start()
    _quote_distinct_timestamps(10_000)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak_bytes > 0

    compute_quote.cache_clear()
    benchmark.pedantic(lambda: _quote_distinct_timestamps(10_000), rounds=1, iterations=1)
    info = compute_quote.cache_info()
    assert info.hits == 0
    assert info.currsize == 10_000
    compute_quote.cache_clear()


def test_price_line_applies_one_discount_per_stack_group() -> None:
    requested_at = datetime(2026, 10, 10, tzinfo=timezone.utc)
    discounts = [
        _discount(
            valid_from=datetime(2026, 10, 1, tzinfo=timezone.utc),
            valid_to=datetime(2026, 11, 1, tzinfo=timezone.utc),
            stack_group="cart",
            value=1000,
        ),
        _discount(
            valid_from=datetime(2026, 10, 1, tzinfo=timezone.utc),
            valid_to=datetime(2026, 11, 1, tzinfo=timezone.utc),
            stack_group="cart",
            kind="fixed",
            value=500,
        ),
        _discount(
            valid_from=datetime(2026, 10, 1, tzinfo=timezone.utc),
            valid_to=datetime(2026, 11, 1, tzinfo=timezone.utc),
            stack_group="member",
            kind="fixed",
            value=100,
        ),
    ]

    result = price_line(1000, 2, discounts, requested_at=requested_at)

    assert result["discount_cents"] == 300
    assert result["total_cents"] == 1700


def test_shipping_discount_only_reduces_shipping_amount() -> None:
    discount = {
        "code": "SHIP100",
        "kind": "shipping",
        "value": 100,
        "min_subtotal_cents": 0,
        "stack_group": None,
        "max_uses": None,
        "used_count": 0,
        "is_active": True,
        "valid_from": None,
        "valid_to": None,
    }

    result = price_line(
        1000,
        1,
        [discount],
        requested_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
        shipping_cents=300,
    )

    assert result["discount_cents"] == 100
    assert result["total_cents"] == 1200


def test_tax_for_line_uses_priority_threshold_and_half_up_rounding() -> None:
    rules = [
        {
            "id": 1,
            "country_code": "DE",
            "region": None,
            "category_id": None,
            "rate_bps": 1000,
            "threshold_cents": None,
            "priority": 1,
            "valid_from": date(2020, 1, 1),
            "valid_to": None,
        },
        {
            "id": 2,
            "country_code": "DE",
            "region": "SN",
            "category_id": 7,
            "rate_bps": 500,
            "threshold_cents": 100,
            "priority": 2,
            "valid_from": date(2020, 1, 1),
            "valid_to": None,
        },
    ]

    tax = tax_for_line(
        210,
        rules,
        country_code="DE",
        region="sn",
        category_id=7,
        as_of=date(2026, 10, 10),
    )

    assert tax == 6


def test_discount_snapshots_are_hashable_quote_cache_inputs() -> None:
    validity = datetime(2026, 10, 10, tzinfo=timezone.utc)
    snapshot = DiscountSnapshot(
        "AUTUMN10",
        "percent",
        1000,
        0,
        None,
        None,
        0,
        True,
        validity,
        None,
    )

    compute_quote.cache_clear()
    first = compute_quote("MUG-WHT", 1, None, "EUR", validity, 1, 1, 850, (snapshot,))
    second = compute_quote("MUG-WHT", 1, None, "EUR", validity, 1, 1, 850, (snapshot,))

    assert first == second == (85, 765)
    assert compute_quote.cache_info().hits == 1
    compute_quote.cache_clear()
