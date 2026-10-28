from __future__ import annotations

import datetime as dt
import random
import string
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.engine import Connection

_CHUNK_SIZE = 5_000
_BASE_TIME = dt.datetime(2026, 10, 10, 8, tzinfo=dt.timezone.utc)
_ORDER_STATUSES = ("confirmed", "picking", "shipped", "delivered")
_COUNTRIES = ("DE", "AT", "NL", "FR")
_CITIES = ("Leipzig", "Berlin", "Hamburg", "Munich")

ProgressCallback = Callable[[str, int], None]


def _timestamp(rng: random.Random, index: int) -> dt.datetime:
    return _BASE_TIME - dt.timedelta(days=rng.randrange(730), minutes=index % 1440)


def _scaled_count(volumes: dict[str, Any], key: str, scale: float) -> int:
    return max(1, round(int(volumes[key]) * scale))


def _next_id(connection: Connection, table: str) -> int:
    connection.execute(text(f'LOCK TABLE "{table}" IN EXCLUSIVE MODE'))
    return int(connection.execute(text(f'SELECT COALESCE(MAX(id), 0) + 1 FROM "{table}"')).scalar_one())


def _copy_rows(
    connection: Connection,
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    row_count: int,
    on_progress: Callable[[int], None],
) -> None:
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
    )
    raw_connection = connection.connection.driver_connection
    copied = 0
    chunk: list[Sequence[Any]] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) == _CHUNK_SIZE:
            with raw_connection.cursor() as cursor:
                with cursor.copy(statement) as copy:
                    for item in chunk:
                        copy.write_row(item)
            copied += len(chunk)
            chunk.clear()
            on_progress(min(99, copied * 100 // row_count))

    if chunk:
        with raw_connection.cursor() as cursor:
            with cursor.copy(statement) as copy:
                for item in chunk:
                    copy.write_row(item)
        copied += len(chunk)
        on_progress(min(99, copied * 100 // row_count))
    if copied != row_count:
        raise RuntimeError(f"Expected {row_count} {table} rows but generated {copied}")
    on_progress(100)


def _insert_domain(
    connection: Connection,
    domain: str,
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    row_count: int,
    progress: ProgressCallback,
) -> None:
    _copy_rows(
        connection,
        table,
        columns,
        rows,
        row_count,
        lambda percentage: progress(domain, percentage),
    )
    connection.execute(
        text(
            "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), "
            f"(SELECT MAX(id) FROM \"{table}\"))"
        ),
        {"table_name": table},
    )


def _category_rows(
    start_id: int,
    tenant_id: int,
    count: int,
    max_depth: int,
    created_at: dt.datetime,
) -> list[tuple[Any, ...]]:
    depth = max(1, min(count, max_depth))
    anchor_ids = [start_id + index for index in range(depth)]
    children_per_anchor = [0] * depth
    rows: list[tuple[Any, ...]] = []
    for index in range(count):
        category_id = start_id + index
        if index < depth:
            parent_id = None if index == 0 else category_id - 1
            category_depth = index
        else:
            anchor_index = (index - depth) % depth
            parent_id = anchor_ids[anchor_index]
            category_depth = anchor_index + 1
            children_per_anchor[anchor_index] += 1
            if children_per_anchor[anchor_index] > 800:
                raise ValueError("Category workload exceeds the supported sibling limit")
        rows.append((
            category_id,
            tenant_id,
            parent_id,
            f"Category {index + 1}",
            f"category-{index + 1:06d}",
            category_depth,
            index,
            created_at,
        ))
    return rows


def _product_sku(index: int, workload: str, rng: random.Random) -> str:
    if workload == "hostile":
        return f"ACM-{index + 1:06d}"
    prefix = "".join(rng.choice(string.ascii_uppercase) for _ in range(3))
    return f"{prefix}-{index + 1:06d}"


def _validate_tenant(connection: Connection, tenant_slug: str) -> int:
    tenant_id = connection.execute(
        text("SELECT id FROM tenants WHERE slug = :slug"),
        {"slug": tenant_slug},
    ).scalar_one_or_none()
    if tenant_id is None:
        raise ValueError(f"Tenant '{tenant_slug}' does not exist; create it with POST /_seed/tenants first")
    user_count = connection.execute(
        text("SELECT COUNT(*) FROM users WHERE tenant_id = :tenant_id"),
        {"tenant_id": tenant_id},
    ).scalar_one()
    if not user_count:
        raise ValueError(f"Tenant '{tenant_slug}' has no users")
    return int(tenant_id)


def tenant_has_workload(connection: Connection, tenant_id: int) -> bool:
    for table in (
        "warehouses",
        "categories",
        "products",
        "customers",
        "tax_rules",
        "discounts",
        "bundles",
        "blocklist_entries",
        "search_terms",
        "orders",
    ):
        if connection.execute(
            text(f'SELECT 1 FROM "{table}" WHERE tenant_id = :tenant_id LIMIT 1'),
            {"tenant_id": tenant_id},
        ).first():
            return True
    return False


def ordered_domains(requested: list[str] | None) -> list[str]:
    order = [
        "tenants",
        "users",
        "warehouses",
        "categories",
        "products",
        "stock",
        "customers",
        "tax",
        "discounts",
        "blocklist",
        "search",
        "orders",
        "fraud",
    ]
    known = set(order)
    selected = set(requested or order)
    unknown = selected - known
    if unknown:
        raise ValueError(f"Unknown seed domains: {', '.join(sorted(unknown))}")

    dependencies = {
        "products": {"categories"},
        "stock": {"warehouses", "products"},
        "tax": {"categories"},
        "discounts": {"products"},
        "orders": {"customers", "products"},
        "fraud": {"blocklist", "orders"},
    }
    pending = list(selected)
    while pending:
        domain = pending.pop()
        for dependency in dependencies.get(domain, set()):
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)

    result = [domain for domain in order if domain in selected]
    if not set(result) - {"tenants", "users"}:
        raise ValueError("At least one workload data domain must be selected")
    return result


def run_workload_seed(
    *,
    connection: Connection,
    workload: str,
    tenant_slug: str,
    scale: float,
    rng_seed: int,
    config: dict[str, Any],
    domains: list[str] | None,
    progress: ProgressCallback,
) -> int:
    tenant_id = _validate_tenant(connection, tenant_slug)
    volumes = config["volumes"]
    selected = ordered_domains(domains)
    rng = random.Random(rng_seed)
    timestamp = _BASE_TIME + dt.timedelta(seconds=rng_seed)

    counts = {
        "warehouses": _scaled_count(volumes, "warehouses", scale),
        "categories": _scaled_count(volumes, "categories", scale),
        "products": _scaled_count(volumes, "products", scale),
        "customers": _scaled_count(volumes, "customers", scale),
        "stock": _scaled_count(volumes, "stock_levels", scale),
        "orders": _scaled_count(volumes, "orders_history", scale),
        "blocklist": _scaled_count(volumes, "blocklist_entries", scale),
        "search": _scaled_count(volumes, "search_terms", scale),
        "tax": _scaled_count(volumes, "tax_rules", scale),
    }
    counts["categories"] = max(1, counts["categories"])
    counts["products"] = max(1, counts["products"])
    counts["customers"] = max(1, counts["customers"])
    counts["orders"] = max(1, counts["orders"])
    counts["warehouses"] = max(
        1,
        counts["warehouses"],
        (counts["stock"] + counts["products"] - 1) // counts["products"],
    )
    counts["warehouses"] = min(counts["warehouses"], int(volumes["warehouses"]))
    counts["stock"] = min(counts["stock"], counts["products"] * counts["warehouses"])
    category_depth = max(1, int(volumes["category_depth"]))
    discounts_per_bundle = max(1, int(volumes["discounts_per_bundle"]))
    bundle_count = max(1, (counts["products"] + 999) // 1000)
    discount_count = bundle_count * discounts_per_bundle

    ids: dict[str, int] = {}
    names = {
        "warehouses": "warehouses",
        "categories": "categories",
        "products": "products",
        "customers": "customers",
        "addresses": "addresses",
        "stock_levels": "stock_levels",
        "tax_rules": "tax_rules",
        "discounts": "discounts",
        "bundles": "bundles",
        "bundle_items": "bundle_items",
        "bundle_discounts": "bundle_discounts",
        "blocklist_entries": "blocklist_entries",
        "search_terms": "search_terms",
        "orders": "orders",
        "order_items": "order_items",
        "fraud_checks": "fraud_checks",
    }
    for key, table in names.items():
        ids[key] = _next_id(connection, table)

    for domain in ("tenants", "users"):
        if domain in selected:
            progress(domain, 100)

    if "warehouses" in selected:
        start = ids["warehouses"]
        rows = (
            (
                start + index,
                tenant_id,
                f"W{index + 1:07d}",
                f"Warehouse {index + 1}",
                _CITIES[index % len(_CITIES)],
                _COUNTRIES[index % len(_COUNTRIES)],
                51.3397 + index * 0.01,
                12.3731 + index * 0.01,
                True,
                timestamp,
            )
            for index in range(counts["warehouses"])
        )
        _insert_domain(
            connection,
            "warehouses",
            "warehouses",
            ("id", "tenant_id", "code", "name", "city", "country_code", "latitude", "longitude", "is_active", "created_at"),
            rows,
            counts["warehouses"],
            progress,
        )

    if "categories" in selected:
        rows = _category_rows(
            ids["categories"],
            tenant_id,
            counts["categories"],
            category_depth,
            timestamp,
        )
        _insert_domain(
            connection,
            "categories",
            "categories",
            ("id", "tenant_id", "parent_id", "name", "slug", "depth", "sort_order", "created_at"),
            rows,
            counts["categories"],
            progress,
        )

    if "products" in selected:
        start = ids["products"]
        category_start = ids["categories"]

        def product_rows() -> Iterable[tuple[Any, ...]]:
            for index in range(counts["products"]):
                product_id = start + index
                yield (
                    product_id,
                    tenant_id,
                    category_start + index % counts["categories"],
                    _product_sku(index, workload, rng),
                    f"Product {index + 1}",
                    f"ParcelPilot catalog item {index + 1}",
                    499 + index % 50_000,
                    "EUR",
                    100 + index % 10_000,
                    True,
                    Jsonb({"department": index % 20}),
                    timestamp,
                )

        _insert_domain(
            connection,
            "products",
            "products",
            ("id", "tenant_id", "category_id", "sku", "name", "description", "base_price_cents", "currency", "weight_grams", "is_active", "attributes", "created_at"),
            product_rows(),
            counts["products"],
            progress,
        )

    if "stock" in selected:
        start = ids["stock_levels"]
        product_start = ids["products"]
        warehouse_start = ids["warehouses"]

        def stock_rows() -> Iterable[tuple[Any, ...]]:
            for index in range(counts["stock"]):
                yield (
                    start + index,
                    product_start + index % counts["products"],
                    warehouse_start + index // counts["products"],
                    10 + index % 500,
                    index % 3,
                    timestamp,
                    timestamp,
                )

        _insert_domain(
            connection,
            "stock",
            "stock_levels",
            ("id", "product_id", "warehouse_id", "quantity_on_hand", "quantity_reserved", "updated_at", "created_at"),
            stock_rows(),
            counts["stock"],
            progress,
        )

    if "customers" in selected:
        start = ids["customers"]
        address_start = ids["addresses"]

        def customer_rows() -> Iterable[tuple[Any, ...]]:
            for index in range(counts["customers"]):
                yield (
                    start + index,
                    tenant_id,
                    f"customer{index + 1:08d}@seed.example",
                    f"Customer {index + 1}",
                    f"+4915{index:08d}",
                    f"seed-customer-{index + 1:08d}",
                    timestamp,
                )

        _insert_domain(
            connection,
            "customers",
            "customers",
            ("id", "tenant_id", "email", "full_name", "phone", "external_ref", "created_at"),
            customer_rows(),
            counts["customers"],
            progress,
        )

        def address_rows() -> Iterable[tuple[Any, ...]]:
            for index in range(counts["customers"]):
                yield (
                    address_start + index,
                    tenant_id,
                    start + index,
                    None,
                    f"{index + 1} Sample Street",
                    None,
                    _CITIES[index % len(_CITIES)],
                    None,
                    f"{10000 + index % 89999:05d}",
                    _COUNTRIES[index % len(_COUNTRIES)],
                    51.0 + (index % 1000) / 10000,
                    12.0 + (index % 1000) / 10000,
                    True,
                    timestamp,
                    timestamp,
                )

        _insert_domain(
            connection,
            "customers",
            "addresses",
            ("id", "tenant_id", "customer_id", "raw_text", "line1", "line2", "city", "region", "postal_code", "country_code", "latitude", "longitude", "is_default", "normalized_at", "created_at"),
            address_rows(),
            counts["customers"],
            progress,
        )

    if "tax" in selected:
        start = ids["tax_rules"]
        category_start = ids["categories"]

        def tax_rows() -> Iterable[tuple[Any, ...]]:
            for index in range(counts["tax"]):
                yield (
                    start + index,
                    tenant_id,
                    _COUNTRIES[index % len(_COUNTRIES)],
                    None,
                    category_start + index % counts["categories"],
                    1900 + index % 800,
                    None,
                    index,
                    dt.date(2020, 1, 1),
                    None,
                    timestamp,
                )

        _insert_domain(
            connection,
            "tax",
            "tax_rules",
            ("id", "tenant_id", "country_code", "region", "category_id", "rate_bps", "threshold_cents", "priority", "valid_from", "valid_to", "created_at"),
            tax_rows(),
            counts["tax"],
            progress,
        )

    if "discounts" in selected:
        discount_start = ids["discounts"]
        bundle_start = ids["bundles"]
        discount_rows = (
            (
                discount_start + index,
                tenant_id,
                f"SEED-{rng_seed}-{index + 1:06d}",
                "percent" if index % 2 == 0 else "fixed",
                5 + index % 26 if index % 2 == 0 else 100 + index % 5000,
                0,
                "seed",
                None,
                0,
                True,
                dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc),
                None,
                timestamp,
            )
            for index in range(discount_count)
        )
        _insert_domain(
            connection,
            "discounts",
            "discounts",
            ("id", "tenant_id", "code", "kind", "value", "min_subtotal_cents", "stack_group", "max_uses", "used_count", "is_active", "valid_from", "valid_to", "created_at"),
            discount_rows,
            discount_count,
            progress,
        )

        _insert_domain(
            connection,
            "discounts",
            "bundles",
            ("id", "tenant_id", "name", "is_active", "created_at"),
            (
                (bundle_start + index, tenant_id, f"Bundle {index + 1}", True, timestamp)
                for index in range(bundle_count)
            ),
            bundle_count,
            progress,
        )
        item_start = ids["bundle_items"]
        _insert_domain(
            connection,
            "discounts",
            "bundle_items",
            ("id", "bundle_id", "product_id", "quantity", "created_at"),
            (
                (
                    item_start + index,
                    bundle_start + index // 2,
                    ids["products"] + index % counts["products"],
                    1 + index % 3,
                    timestamp,
                )
                for index in range(bundle_count * 2)
            ),
            bundle_count * 2,
            progress,
        )
        bundle_discount_start = ids["bundle_discounts"]
        _insert_domain(
            connection,
            "discounts",
            "bundle_discounts",
            ("id", "bundle_id", "discount_id", "created_at"),
            (
                (
                    bundle_discount_start + index,
                    bundle_start + index // discounts_per_bundle,
                    discount_start + index,
                    timestamp,
                )
                for index in range(discount_count)
            ),
            discount_count,
            progress,
        )

    if "blocklist" in selected:
        start = ids["blocklist_entries"]
        kinds = ("email", "ip", "address", "name", "phone")
        _insert_domain(
            connection,
            "blocklist",
            "blocklist_entries",
            ("id", "tenant_id", "entry_type", "value", "reason", "source", "expires_at", "created_at"),
            (
                (
                    start + index,
                    tenant_id,
                    kinds[index % len(kinds)],
                    f"{kinds[index % len(kinds)]}-{rng_seed}-{index:08d}",
                    "Seeded risk indicator",
                    "seed",
                    None,
                    timestamp,
                )
                for index in range(counts["blocklist"])
            ),
            counts["blocklist"],
            progress,
        )

    if "search" in selected:
        start = ids["search_terms"]
        _insert_domain(
            connection,
            "search",
            "search_terms",
            ("id", "tenant_id", "term", "is_active", "created_at"),
            (
                (start + index, tenant_id, f"catalog term {index + 1:06d}", True, timestamp)
                for index in range(counts["search"])
            ),
            counts["search"],
            progress,
        )

    if "orders" in selected:
        order_start = ids["orders"]
        item_start = ids["order_items"]
        customers_start = ids["customers"]
        addresses_start = ids["addresses"]
        products_start = ids["products"]
        sku_rng = random.Random(rng_seed)
        skus = [_product_sku(index, workload, sku_rng) for index in range(counts["products"])]

        def order_rows() -> Iterable[tuple[Any, ...]]:
            for index in range(counts["orders"]):
                decision = "block" if index % 100 == 0 else "review" if index % 100 == 1 else "allow"
                placed_at = _timestamp(rng, index)
                product_index = index % counts["products"]
                quantity = 1 + index % 3
                subtotal = (499 + product_index % 50_000) * quantity
                yield (
                    order_start + index,
                    tenant_id,
                    customers_start + index % counts["customers"],
                    addresses_start + index % counts["customers"],
                    f"seed-order-{index + 1:09d}",
                    "api",
                    "fraud_review" if decision != "allow" else _ORDER_STATUSES[index % len(_ORDER_STATUSES)],
                    "EUR",
                    subtotal,
                    0,
                    0,
                    499,
                    subtotal + 499,
                    decision,
                    10.0 if decision == "allow" else 70.0 if decision == "review" else 95.0,
                    f"192.0.2.{index % 254 + 1}",
                    None,
                    Jsonb({"seed": rng_seed, "order_index": index}),
                    placed_at,
                    placed_at,
                    timestamp,
                )

        _insert_domain(
            connection,
            "orders",
            "orders",
            ("id", "tenant_id", "customer_id", "shipping_address_id", "external_ref", "source", "status", "currency", "subtotal_cents", "discount_cents", "tax_cents", "shipping_cents", "total_cents", "fraud_decision", "fraud_score", "client_ip", "notes", "raw_payload", "placed_at", "updated_at", "created_at"),
            order_rows(),
            counts["orders"],
            progress,
        )

        def order_item_rows() -> Iterable[tuple[Any, ...]]:
            for index in range(counts["orders"]):
                order_id = order_start + index
                product_index = index % counts["products"]
                price = 499 + product_index % 50_000
                quantity = 1 + index % 3
                yield (
                    item_start + index,
                    order_id,
                    products_start + product_index,
                    skus[product_index],
                    quantity,
                    price,
                    0,
                    0,
                    price * quantity,
                    False,
                    timestamp,
                )

        _insert_domain(
            connection,
            "orders",
            "order_items",
            ("id", "order_id", "product_id", "sku", "quantity", "unit_price_cents", "discount_cents", "tax_cents", "line_total_cents", "normalized", "created_at"),
            order_item_rows(),
            counts["orders"],
            progress,
        )

    if "fraud" in selected:
        start = ids["fraud_checks"]
        order_start = ids["orders"]
        blocklist_start = ids["blocklist_entries"]
        _insert_domain(
            connection,
            "fraud",
            "fraud_checks",
            ("id", "tenant_id", "order_id", "input_snapshot", "score", "decision", "matched_entry_ids", "duration_ms", "created_at"),
            (
                (
                    start + index,
                    tenant_id,
                    order_start + index,
                    Jsonb({"client_ip": f"192.0.2.{index % 254 + 1}"}),
                    10.0 if index % 100 > 1 else 70.0 if index % 100 == 1 else 95.0,
                    "allow" if index % 100 > 1 else "review" if index % 100 == 1 else "block",
                    Jsonb([] if index % 100 > 1 else [blocklist_start + index % counts["blocklist"]]),
                    1 + index % 25,
                    timestamp,
                )
                for index in range(counts["orders"])
            ),
            counts["orders"],
            progress,
        )

    return tenant_id
