from __future__ import annotations

import datetime as dt

from parcelpilot.dev.seeder import _category_rows, ordered_domains
from parcelpilot.dev.workloads import WORKLOADS, validate_workloads
from profiling.run import SEED_DOMAINS


def test_workload_definitions_allow_sku_metadata() -> None:
    assert validate_workloads() is WORKLOADS
    typical_stock = WORKLOADS["typical"]["volumes"]["stock_levels"]
    hostile_stock = WORKLOADS["hostile"]["volumes"]["stock_levels"]
    assert typical_stock > hostile_stock


def test_seed_domains_include_dependencies_in_build_order() -> None:
    domains = ordered_domains(["fraud"])

    assert domains == [
        "categories",
        "products",
        "customers",
        "blocklist",
        "orders",
        "fraud",
    ]


def test_profile_runner_only_requests_supported_seed_domains() -> None:
    assert ordered_domains(SEED_DOMAINS)


def test_category_generation_is_deterministic_and_respects_depth() -> None:
    created_at = dt.datetime(2026, 10, 10, tzinfo=dt.timezone.utc)
    first = _category_rows(10, 7, 5_000, 40, created_at)
    second = _category_rows(10, 7, 5_000, 40, created_at)

    assert first == second
    assert max(row[5] for row in first) == 40
    assert sum(row[2] is None for row in first) == 1
    assert len(first) == 5_000
