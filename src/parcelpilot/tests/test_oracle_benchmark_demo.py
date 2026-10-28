from __future__ import annotations

import pytest

from parcelpilot.tests.bench import load_benchmark_threshold, record_benchmark_result
from parcelpilot.tests.oracle_helpers import (
    compare_exact,
    compare_float_tolerance,
    compare_set_equal,
    compare_unordered,
    load_oracle,
    write_oracle,
)


def repeated_pass(values: list[int]) -> int:
    first_pass = sum(values)
    second_pass = sum(values)
    return first_pass + second_pass


@pytest.mark.oracle
def test_oracle_helpers_round_trip() -> None:
    oracle_payload = {"expected": [1, 2, 3], "amount": 12.345, "tags": ["alpha", "beta", "gamma"]}
    write_oracle("demo_case", oracle_payload)
    loaded = load_oracle("demo_case")

    assert compare_exact(loaded["expected"], [1, 2, 3])
    assert compare_float_tolerance(loaded["amount"], 12.345, atol=1e-6)
    assert compare_unordered(loaded["tags"], ["gamma", "alpha", "beta"])
    assert compare_set_equal({"alpha", "beta", "gamma"}, {"gamma", "alpha", "beta"})


@pytest.mark.tripwire
def test_tripwire_repeated_pass_stays_present() -> None:
    values = [1, 2, 3, 4]
    observed = repeated_pass(values)

    assert observed == 20
    assert observed > sum(values)


@pytest.mark.bench
def test_benchmark_helper_records_result(benchmark: pytest.BenchmarkFixture) -> None:
    benchmark.pedantic(lambda: sum(range(1_000)), rounds=5, iterations=100)

    sample = [11.2, 11.7, 12.0, 12.6]
    result_path = record_benchmark_result(
        "demo_case",
        median_ms=12.0,
        samples_ms=sample,
        threshold=20.0,
        metadata={"source": "toy benchmark fixture"},
    )

    assert result_path.exists()
    assert load_benchmark_threshold("demo_case") in {None, 20.0}
