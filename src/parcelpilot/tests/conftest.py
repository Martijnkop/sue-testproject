from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def ephemeral_db() -> dict[str, Any]:
    return {
        "url": "sqlite:///:memory:",
        "dialect": "sqlite",
        "role": "test",
    }


@pytest.fixture
def seeded_benign() -> dict[str, Any]:
    return {
        "tenant_slug": "benign-demo",
        "scale": 0.1,
        "rng_seed": 7,
        "domains": ["customers", "warehouses"],
    }


@pytest.fixture
def seeded_hostile() -> dict[str, Any]:
    return {
        "tenant_slug": "hostile-demo",
        "scale": 1.0,
        "rng_seed": 13,
        "domains": ["catalog", "orders", "fraud"],
    }


@pytest.fixture
def authenticated_client() -> dict[str, Any]:
    return {
        "base_url": "http://testserver",
        "role": "admin",
        "token": "demo-token",
        "headers": {"Authorization": "Bearer demo-token"},
    }
