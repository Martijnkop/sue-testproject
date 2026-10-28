from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from parcelpilot.config.lists import BLOCKLISTS
from parcelpilot.fraud import repository
from parcelpilot.fraud.lookup import reload_blocklists
from parcelpilot.fraud.screening import screen_order
from parcelpilot.tests.bench import load_benchmark_threshold
from parcelpilot.tests.oracle_helpers import load_oracle


@pytest.fixture
def oracle_entries() -> list[dict[str, Any]]:
    rows = load_oracle("H2")["entries"]
    for row in rows:
        expiry = row["expires_at"]
        row["expires_at"] = datetime.fromisoformat(expiry.replace("Z", "+00:00")) if expiry else None
    reload_blocklists(rows)
    return rows


@pytest.mark.oracle
def test_screening_matches_h2_oracle_for_two_thousand_orders(
    oracle_entries: list[dict[str, Any]],
) -> None:
    cases = load_oracle("H2")["cases"]
    results = []
    for index in range(2000):
        case = cases[index % len(cases)]
        result = screen_order(case["payload"], 1)
        results.append(
            {
                "decision": result["decision"],
                "score": result["score"],
                "matches": result["matches"],
            }
        )

    expected_cases = [
        {
            "decision": case["decision"],
            "score": case["score"],
            "matches": case["matches"],
        }
        for case in cases
    ]
    assert results == [expected_cases[index % len(expected_cases)] for index in range(2000)]
    assert oracle_entries


@pytest.mark.tripwire
def test_blocklist_values_remain_lists() -> None:
    assert type(BLOCKLISTS["email"]) is list


def test_blocklist_repository_scopes_entries_and_filters_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(repository, "_ENTRIES", {})
    monkeypatch.setattr(repository, "_ENTRY_SEQUENCE", 0)
    now_past = datetime(2000, 1, 1, tzinfo=timezone.utc)

    created, skipped = repository.add_entries(
        1,
        [
            {"entry_type": "email", "value": "MIA@EXAMPLE.COM", "reason": "known", "expires_at": None},
            {"entry_type": "email", "value": "mia@example.com", "reason": "duplicate", "expires_at": None},
            {"entry_type": "phone", "value": "+1 555 123", "reason": "expired", "expires_at": now_past},
        ],
    )
    global_created, _ = repository.add_entries(
        None,
        [{"entry_type": "ip", "value": "203.0.113.9", "reason": "global", "expires_at": None}],
    )

    assert (created, skipped, global_created) == (2, 1, 1)
    assert len(repository.list_entries(1, include_expired=False)) == 2
    assert len(repository.list_entries(1, include_expired=True)) == 3
    assert len(repository.list_entries(2, include_expired=False)) == 1
    assert screen_order({"email": "mia@example.com"}, 2)["matches"] == []
    assert screen_order({"ip_address": "203.0.113.9"}, 2)["matches"][0]["reason"] == "global"


@pytest.mark.bench
def test_fraud_screening_hostile_benchmark(benchmark: pytest.BenchmarkFixture) -> None:
    assert load_benchmark_threshold("H2") == 50.0
    assert load_benchmark_threshold("P1") == 50.0
    rows = [
        {
            "id": index + 1,
            "tenant_id": 1,
            "entry_type": "email",
            "value": f"blocked-{index}@example.com",
            "reason": "hostile profile",
            "expires_at": None,
        }
        for index in range(100_000)
    ]
    rows[-1]["value"] = "last-blocked@example.com"
    reload_blocklists(rows)
    orders = [
        {"email": "last-blocked@example.com", "phone": f"+1 555 {index:07d}"}
        for index in range(2000)
    ]

    results = benchmark.pedantic(
        lambda: [screen_order(order, 1) for order in orders],
        rounds=1,
        iterations=1,
    )
    assert len(results) == 2000
