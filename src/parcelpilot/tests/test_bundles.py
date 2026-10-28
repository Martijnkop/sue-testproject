from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from parcelpilot.pricing.bundles import best_combination, create_bundle, get_bundle
from parcelpilot.tests.bench import load_benchmark_threshold
from parcelpilot.tests.oracle_helpers import load_oracle


def _candidates() -> list[dict[str, Any]]:
    baseline = {
        "min_subtotal_cents": 0,
        "stack_group": None,
        "max_uses": None,
        "used_count": 0,
        "is_active": True,
        "valid_from": None,
        "valid_to": None,
    }
    return [
        {**baseline, "id": 1, "code": "AUTUMN10", "kind": "percent", "value": 1000, "stack_group": "percent"},
        {**baseline, "id": 2, "code": "SAVE2", "kind": "fixed", "value": 200, "stack_group": "fixed"},
        {**baseline, "id": 3, "code": "SAVE5", "kind": "fixed", "value": 500, "stack_group": "fixed"},
        {**baseline, "id": 4, "code": "MINIMUM", "kind": "fixed", "value": 1000, "min_subtotal_cents": 4000},
        {**baseline, "id": 5, "code": "INACTIVE", "kind": "fixed", "value": 900, "is_active": False},
        {**baseline, "id": 6, "code": "SHIP", "kind": "shipping", "value": 1000},
        {**baseline, "id": 7, "code": "FUTURE", "kind": "fixed", "value": 800, "valid_from": datetime(2030, 1, 1, tzinfo=timezone.utc)},
        {**baseline, "id": 8, "code": "EXPIRED", "kind": "fixed", "value": 700, "valid_to": datetime(2020, 1, 1, tzinfo=timezone.utc)},
    ]


@pytest.mark.oracle
def test_best_combination_matches_p4_oracle() -> None:
    actual = best_combination(
        3100,
        _candidates(),
        6,
        requested_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
    )

    assert actual == load_oracle("P4")


def test_bundle_creation_normalizes_items_and_is_tenant_scoped() -> None:
    products = {
        "MUG-WHT": {
            "id": 1,
            "base_price_cents": 850,
            "is_active": True,
        }
    }
    discounts = {12: {"id": 12}}

    created = create_bundle(
        901,
        "Breakfast set",
        [{"sku": " mug-wht ", "quantity": 2}],
        [12],
        products,
        discounts,
    )

    assert created["items"] == [{"sku": "MUG-WHT", "quantity": 2}]
    assert get_bundle(901, created["id"]) == created
    assert get_bundle(902, created["id"]) is None


def test_best_combination_breaks_savings_ties_by_discount_ids() -> None:
    candidates = [
        {
            **_candidates()[0],
            "id": 9,
            "code": "LATE",
            "kind": "fixed",
            "value": 500,
            "stack_group": None,
        },
        {
            **_candidates()[0],
            "id": 3,
            "code": "EARLY",
            "kind": "fixed",
            "value": 500,
            "stack_group": None,
        },
    ]

    result = best_combination(1000, candidates, 2)

    assert result["best_combination"] == [
        {"discount_id": 3, "code": "EARLY", "savings_cents": 500}
    ]


@pytest.mark.tripwire
@pytest.mark.parametrize("candidate_count", [0, 1, 8, 18])
def test_best_combination_evaluates_every_subset(candidate_count: int) -> None:
    candidates = _candidates()[:candidate_count]
    if candidate_count > len(candidates):
        candidates.extend(
            {
                **_candidates()[0],
                "id": index + 1,
                "code": f"EXTRA{index}",
            }
            for index in range(len(candidates), candidate_count)
        )

    result = best_combination(3100, candidates, 6)

    assert result["combinations_evaluated"] == 2**candidate_count


@pytest.mark.bench
def test_best_combination_hostile_benchmark(benchmark: pytest.BenchmarkFixture) -> None:
    assert load_benchmark_threshold("P4") == 50.0
    candidates = [
        {
            **_candidates()[0],
            "id": index + 1,
            "code": f"HOSTILE{index}",
            "value": 250 + index,
            "stack_group": f"group-{index % 6}",
            "min_subtotal_cents": index * 10,
        }
        for index in range(18)
    ]

    result = benchmark.pedantic(
        lambda: best_combination(3100, candidates, 6),
        rounds=1,
        iterations=1,
    )
    assert result["combinations_evaluated"] == 2**18
