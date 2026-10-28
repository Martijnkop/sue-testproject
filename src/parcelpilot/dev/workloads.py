from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency for YAML parsing
    yaml = None

WORKLOADS: dict[str, dict[str, Any]] = {
    "benign": {
        "scale": 0.1,
        "rng_seed": 101,
        "volumes": {
            "warehouses": 4,
            "customers": 2_000,
            "categories": 100,
            "category_depth": 3,
            "products": 5_000,
            "sku_scheme": "random 3-letter prefix + number",
            "stock_levels": 20_000,
            "orders_history": 20_000,
            "blocklist_entries": 1_000,
            "search_terms": 50,
            "tax_rules": 20,
            "discounts_per_bundle": 8,
            "import_rows": 10_000,
            "shipment_events": 50_000,
            "bins_per_warehouse": 500,
            "route_stops": 50,
        },
    },
    "typical": {
        "scale": 0.5,
        "rng_seed": 202,
        "volumes": {
            "warehouses": 4,
            "customers": 30_000,
            "categories": 500,
            "category_depth": 5,
            "products": 20_000,
            "sku_scheme": "random 3-letter prefix + number",
            "stock_levels": 80_000,
            "orders_history": 300_000,
            "blocklist_entries": 20_000,
            "search_terms": 500,
            "tax_rules": 200,
            "discounts_per_bundle": 10,
            "import_rows": 200_000,
            "shipment_events": 500_000,
            "bins_per_warehouse": 2_000,
            "route_stops": 300,
        },
    },
    "hostile": {
        "scale": 1.0,
        "rng_seed": 303,
        "volumes": {
            "warehouses": 1,
            "customers": 200_000,
            "categories": 5_000,
            "category_depth": 40,
            "max_siblings_per_node": 800,
            "products": 50_000,
            "sku_scheme": "one shared prefix (ACM-000001)",
            "stock_levels": 50_000,
            "orders_history": 1_000_000,
            "blocklist_entries": 100_000,
            "search_terms": 5_000,
            "tax_rules": 2_000,
            "discounts_per_bundle": 18,
            "import_rows": 2_000_000,
            "shipment_events": 5_000_000,
            "bins_per_warehouse": 5_000,
            "route_stops": 1_500,
        },
    },
}

WORKLOAD_ORDER = ("benign", "typical", "hostile")
_MIN_SCALE = 0.01
_MAX_SCALE = 1.0


def _validate_monotonic_selection(data: dict[str, dict[str, Any]]) -> None:
    expected_pairs = {
        "customers": ("benign", "typical", "hostile"),
        "categories": ("benign", "typical", "hostile"),
        "products": ("benign", "typical", "hostile"),
        "orders_history": ("benign", "typical", "hostile"),
        "blocklist_entries": ("benign", "typical", "hostile"),
        "search_terms": ("benign", "typical", "hostile"),
        "tax_rules": ("benign", "typical", "hostile"),
        "discounts_per_bundle": ("benign", "typical", "hostile"),
        "import_rows": ("benign", "typical", "hostile"),
        "shipment_events": ("benign", "typical", "hostile"),
        "bins_per_warehouse": ("benign", "typical", "hostile"),
        "route_stops": ("benign", "typical", "hostile"),
    }

    for key, workload_names in expected_pairs.items():
        values = [data[name]["volumes"][key] for name in workload_names]
        if not all(value > 0 for value in values):
            raise ValueError(f"Workload volume {key!r} must be positive for each workload")
        if not values[0] <= values[1] <= values[2]:
            raise ValueError(f"Workload volume {key!r} should be monotone benign <= typical <= hostile")


def validate_workloads(data: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    payload = data or WORKLOADS

    if set(payload) != set(WORKLOAD_ORDER):
        raise ValueError(f"Workloads must contain exactly {WORKLOAD_ORDER!r}")

    for workload_name in WORKLOAD_ORDER:
        workload = payload[workload_name]
        if "scale" not in workload or "rng_seed" not in workload or "volumes" not in workload:
            raise ValueError(f"Workload {workload_name!r} is missing scale, rng_seed, or volumes")

        scale = workload["scale"]
        if not isinstance(scale, (int, float)) or not (_MIN_SCALE <= scale <= _MAX_SCALE):
            raise ValueError(f"Workload {workload_name!r} scale must be between 0.01 and 1.0")

        rng_seed = workload["rng_seed"]
        if not isinstance(rng_seed, int):
            raise ValueError(f"Workload {workload_name!r} rng_seed must be an integer")

        volumes = workload["volumes"]
        if not volumes or not all(
            (isinstance(value, int) and value > 0)
            or (key == "sku_scheme" and isinstance(value, str) and value)
            for key, value in volumes.items()
        ):
            raise ValueError(f"Workload {workload_name!r} volumes must contain positive integers and valid metadata")

    _validate_monotonic_selection(payload)
    return payload


def load_workloads(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    if path is None:
        return validate_workloads(WORKLOADS)

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Workloads file not found: {config_path}")

    if yaml is None:
        raise RuntimeError("PyYAML is required to load workload definitions from YAML")

    with config_path.open("r", encoding="utf-8") as handle:
        contents = yaml.safe_load(handle)

    return validate_workloads(contents.get("workloads", contents))
