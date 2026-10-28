from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from parcelpilot.analytics import daily, tax
from parcelpilot.imports import normalize, repository
from parcelpilot.reports import models as report_models
from parcelpilot.reports import service as report_service
from parcelpilot.reports.models import Report
from parcelpilot.tests.bench import load_benchmark_threshold
from parcelpilot.tests.oracle_helpers import load_oracle


@pytest.mark.oracle
@pytest.mark.tripwire
def test_import_normalization_matches_oracle_and_calls_price_cleaner_once_per_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = load_oracle("P2")
    monkeypatch.setattr(repository, "_JOBS", {})
    job = repository.create_job(1, 1, "normalization.csv", "csv", False, {"normalization": {}})
    row_count = 10_000
    repository.append_rows(1, job["id"], [
        {
            "row_number": index,
            "raw": {
                "unit_price": "1,299.50" if index % 2 == 0 else "19.90",
                "ship_postal_code": " 04229 ",
                "ship_city": "leipzig",
                "ship_country": "de",
            },
            "status": "imported",
            "error": None,
            "order_id": None,
        }
        for index in range(row_count)
    ])
    calls = 0
    original_to_cents = normalize.cleaners.to_cents

    def counted_to_cents(value: str) -> int:
        nonlocal calls
        calls += 1
        return original_to_cents(value)

    monkeypatch.setattr(normalize.cleaners, "to_cents", counted_to_cents)
    result = normalize.normalize_job(1, job["id"])
    normalized = repository.get_job(1, job["id"])["rows"]

    assert result == {"normalized_rows": row_count}
    assert calls == row_count
    assert normalized[0]["raw"]["unit_price_cents"] == expected["thousands_separator_cents"]
    assert normalized[1]["raw"]["unit_price_cents"] == expected["trailing_zero_cents"]
    assert normalized[0]["raw"]["ship_postal_code"] == expected["postal_code"]
    assert normalized[0]["raw"]["ship_city"] == expected["city"]


@pytest.mark.oracle
@pytest.mark.tripwire
def test_report_page_order_is_stable_and_exposes_repeated_property_sort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = load_oracle("H1")
    report = Report(1, 1, {}, [
        {"group_key": "b", "label": "beta", "orders_count": 1, "units": 2, "revenue_cents": 10},
        {"group_key": "a1", "label": "Alpha", "orders_count": 1, "units": 1, "revenue_cents": 10},
        {"group_key": "a2", "label": "alpha", "orders_count": 2, "units": 1, "revenue_cents": 10},
    ])
    calls = 0
    original_sorted = sorted

    def counted_sorted(*args: Any, **kwargs: Any) -> list[Any]:
        nonlocal calls
        calls += 1
        return original_sorted(*args, **kwargs)

    monkeypatch.setattr(report_models, "sorted", counted_sorted, raising=False)
    expected_orders = {
        ("label", "asc"): expected["label_order"] + ["b"],
        ("label", "desc"): ["b", "a1", "a2"],
        ("revenue_cents", "asc"): ["b", "a1", "a2"],
        ("revenue_cents", "desc"): ["b", "a1", "a2"],
        ("orders_count", "asc"): ["b", "a1", "a2"],
        ("orders_count", "desc"): ["a2", "b", "a1"],
        ("units", "asc"): ["a1", "a2", "b"],
        ("units", "desc"): ["b", "a1", "a2"],
    }
    for (sort_by, order), expected_keys in expected_orders.items():
        items, total = report_service.render_page(report, sort_by=sort_by, order=order, limit=3, offset=0)
        assert [item["group_key"] for item in items] == expected_keys
        assert [item["rank"] for item in items] == [1, 2, 3]
        assert total == 3
    assert calls >= len(expected_orders) * 3


@pytest.mark.oracle
def test_daily_analytics_keeps_integer_totals_and_expected_net(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = load_oracle("H10")
    summary_date = date(2026, 10, 10)
    order = {
        "id": 12,
        "currency": "EUR",
        "placed_at": datetime(2026, 10, 10, tzinfo=timezone.utc),
        "items": [
            {"sku": "ONE", "quantity": 2, "unit_price_cents": 1000, "discount_cents": 100, "tax_cents": 171},
            {"sku": "TWO", "quantity": 1, "unit_price_cents": 500, "discount_cents": 0, "tax_cents": 95},
        ],
    }
    monkeypatch.setattr(daily, "_SUMMARIES", {})
    monkeypatch.setattr(daily.order_repo, "list_for_tenant", lambda tenant_id: [order])
    monkeypatch.setattr(daily, "_PRODUCTS", {
        "ONE": {"category_id": 1},
        "TWO": {"category_id": 2},
    })

    summaries, written = daily.compute_daily(1, summary_date, summary_date, "EUR", True)

    assert written == 1
    assert len(summaries) == 1
    assert summaries[0]["orders_count"] == expected["orders_count"]
    assert summaries[0]["items_count"] == expected["items_count"]
    assert summaries[0]["gross_cents"] == expected["gross_cents"]
    assert summaries[0]["discount_cents"] == expected["discount_cents"]
    assert summaries[0]["tax_cents"] == expected["tax_cents"]
    assert summaries[0]["net_cents"] == expected["net_cents"]
    assert all(type(summaries[0][key]) is int for key in (
        "orders_count", "items_count", "gross_cents", "discount_cents", "tax_cents", "net_cents"
    ))


@pytest.mark.oracle
def test_tax_estimate_preserves_half_up_rounding_thresholds_and_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = load_oracle("H9")
    monkeypatch.setattr(tax.order_service, "_TAX_RULES", {1: [
        {
            "id": 4, "country_code": "DE", "region": None, "category_id": 7,
            "rate_bps": 5000, "threshold_cents": 5, "priority": 2,
            "valid_from": date(2020, 1, 1), "valid_to": None,
        },
        {
            "id": 5, "country_code": "DE", "region": None, "category_id": 7,
            "rate_bps": 1000, "threshold_cents": 0, "priority": 1,
            "valid_from": date(2020, 1, 1), "valid_to": None,
        },
        {
            "id": 6, "country_code": "DE", "region": None, "category_id": 7,
            "rate_bps": 3000, "threshold_cents": 0, "priority": 2,
            "valid_from": date(2020, 1, 1), "valid_to": None,
        },
    ]})

    result = tax.estimate(1, "DE", None, [
        {"amount_cents": 10, "category_id": 7},
        {"amount_cents": 15, "category_id": 7},
    ])

    assert result == expected


@pytest.mark.bench
def test_sales_report_page_benchmark(benchmark: pytest.BenchmarkFixture) -> None:
    assert load_benchmark_threshold("H1") == 10.0
    report = Report(1, 1, {}, [
        {"group_key": str(index), "label": f"Product {index}", "orders_count": index, "units": index, "revenue_cents": index}
        for index in range(50_000)
    ])
    result = benchmark.pedantic(
        lambda: report_service.render_page(report, sort_by="revenue_cents", order="desc", limit=500, offset=0),
        rounds=1,
        iterations=1,
    )
    assert len(result[0]) == 500


@pytest.mark.bench
def test_import_normalization_benchmark(benchmark: pytest.BenchmarkFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_benchmark_threshold("P2") == 3.0
    monkeypatch.setattr(repository, "_JOBS", {})
    job = repository.create_job(1, 1, "large.csv", "csv", False, {"normalization": {}})
    count = 200_000
    repository.append_rows(1, job["id"], [
        {"row_number": index, "raw": {"unit_price": "19.99", "ship_postal_code": " 04229 ", "ship_city": "leipzig", "ship_country": "de"},
         "status": "imported", "error": None, "order_id": None}
        for index in range(count)
    ])
    result = benchmark.pedantic(lambda: normalize.normalize_job(1, job["id"]), rounds=1, iterations=1)
    assert result["normalized_rows"] == count


@pytest.mark.bench
def test_daily_analytics_benchmark(benchmark: pytest.BenchmarkFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_benchmark_threshold("H10") == 5.0
    orders: list[dict[str, Any]] = []
    products: dict[str, dict[str, int]] = {}
    start_date = date(2026, 1, 1)
    for index in range(55_000):
        sku = f"SKU-{index}"
        products[sku] = {"category_id": index}
        orders.append({
            "id": index + 1, "currency": "EUR",
            "placed_at": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index % 270),
            "items": [{"sku": sku, "quantity": 1, "unit_price_cents": 100, "discount_cents": 0, "tax_cents": 19}],
        })
    monkeypatch.setattr(daily.order_repo, "list_for_tenant", lambda tenant_id: orders)
    monkeypatch.setattr(daily, "_PRODUCTS", products)
    frame = benchmark.pedantic(
        lambda: daily.compute_range(1, start_date, date(2026, 9, 27), "EUR"),
        rounds=1,
        iterations=1,
    )
    assert len(frame) == 55_000


@pytest.mark.bench
def test_tax_estimate_benchmark(benchmark: pytest.BenchmarkFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_benchmark_threshold("H9") == 20.0
    monkeypatch.setattr(tax.order_service, "_TAX_RULES", {1: [
        {"id": 1, "country_code": "DE", "region": None, "category_id": 7, "rate_bps": 1900,
         "threshold_cents": None, "priority": 0, "valid_from": date(2020, 1, 1), "valid_to": None}
    ]})
    lines = [{"amount_cents": 3598 + index % 10, "category_id": 7} for index in range(100_000)]
    result = benchmark.pedantic(lambda: tax.estimate(1, "DE", None, lines), rounds=1, iterations=1)
    assert len(result["lines"]) == 100_000
