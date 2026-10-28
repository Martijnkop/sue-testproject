from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261010_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False, unique=True),
        sa.Column("plan", sa.String(length=20), nullable=False, server_default="standard"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"], unique=False)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("external_ref", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "email", name="uq_customers_tenant_email"),
        sa.UniqueConstraint("tenant_id", "external_ref", name="uq_customers_tenant_external_ref"),
    )
    op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"], unique=False)

    op.create_table(
        "addresses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("line1", sa.String(length=200), nullable=False),
        sa.Column("line2", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.Column("country_code", sa.CHAR(length=2), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("shipping_address_id", sa.BigInteger(), sa.ForeignKey("addresses.id"), nullable=False),
        sa.Column("external_ref", sa.String(length=100), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="api"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("subtotal_cents", sa.BigInteger(), nullable=False),
        sa.Column("discount_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tax_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("shipping_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("fraud_decision", sa.String(length=20), nullable=True),
        sa.Column("fraud_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("client_ip", sa.String(length=45), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "external_ref", name="uq_orders_tenant_external_ref"),
    )
    op.create_index("ix_orders_tenant_status", "orders", ["tenant_id", "status"], unique=False)
    op.create_index("ix_orders_tenant_placed_at", "orders", ["tenant_id", "status", "placed_at"], unique=False)
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"], unique=False)

    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("depth", sa.SmallInteger(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_categories_tenant_slug"),
    )
    op.create_index("ix_categories_tenant_parent", "categories", ["tenant_id", "parent_id"], unique=False)

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("category_id", sa.BigInteger(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("weight_grams", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "sku", name="uq_products_tenant_sku"),
    )
    op.create_index("ix_products_tenant_category", "products", ["tenant_id", "category_id"], unique=False)
    op.create_index("ix_products_tenant_active", "products", ["tenant_id", "is_active"], unique=False)

    op.create_table(
        "order_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("discount_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tax_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("line_total_cents", sa.BigInteger(), nullable=False),
        sa.Column("normalized", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"], unique=False)
    op.create_index("ix_order_items_product_id", "order_items", ["product_id"], unique=False)

    op.create_table(
        "import_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("params", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orders_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "import_rows",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.BigInteger(), sa.ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("job_id", "row_number", name="uq_import_rows_job_row_number"),
    )
    op.create_index("ix_import_rows_job_status", "import_rows", ["job_id", "status"], unique=False)

    op.create_table(
        "blocklist_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.String(length=320), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "entry_type", "value", name="uq_blocklist_tenant_entry_type_value"),
    )
    op.create_index("ix_blocklist_entry_type_value", "blocklist_entries", ["entry_type", "value"], unique=False)

    op.create_table(
        "fraud_checks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("input_snapshot", sa.JSON(), nullable=True),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("matched_entry_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_fraud_checks_order_id", "fraud_checks", ["order_id"], unique=False)

    op.create_table(
        "warehouses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("country_code", sa.CHAR(length=2), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),
    )
    op.create_index("ix_warehouses_tenant_active", "warehouses", ["tenant_id", "is_active"], unique=False)

    op.create_table(
        "stock_levels",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("quantity_on_hand", sa.Integer(), nullable=False),
        sa.Column("quantity_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("product_id", "warehouse_id", name="uq_stock_levels_product_warehouse"),
    )
    op.create_index("ix_stock_levels_warehouse_id", "stock_levels", ["warehouse_id"], unique=False)

    op.create_table(
        "search_terms",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("term", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "term", name="uq_search_terms_tenant_term"),
    )

    op.create_table(
        "product_tags",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term_id", sa.BigInteger(), sa.ForeignKey("search_terms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("product_id", "term_id", name="uq_product_tags_product_term"),
    )
    op.create_index("ix_product_tags_term_id", "product_tags", ["term_id"], unique=False)

    op.create_table(
        "discounts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column("min_subtotal_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("stack_group", sa.String(length=50), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_discounts_tenant_code"),
    )

    op.create_table(
        "bundles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "bundle_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("bundle_id", sa.BigInteger(), sa.ForeignKey("bundles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("bundle_id", "product_id", name="uq_bundle_items_bundle_product"),
    )

    op.create_table(
        "bundle_discounts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("bundle_id", sa.BigInteger(), sa.ForeignKey("bundles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("discount_id", sa.BigInteger(), sa.ForeignKey("discounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("bundle_id", "discount_id", name="uq_bundle_discounts_bundle_discount"),
    )

    op.create_table(
        "price_quotes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("discount_codes", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("discount_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_price_quotes_tenant_requested_at", "price_quotes", ["tenant_id", "requested_at"], unique=False)

    op.create_table(
        "tax_rules",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("country_code", sa.CHAR(length=2), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("category_id", sa.BigInteger(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("rate_bps", sa.Integer(), nullable=False),
        sa.Column("threshold_cents", sa.BigInteger(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tax_rules_tenant_country_valid_from", "tax_rules", ["tenant_id", "country_code", "valid_from"], unique=False)

    op.create_table(
        "shipments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("carrier", sa.String(length=50), nullable=False),
        sa.Column("tracking_number", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="created"),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "tracking_number", name="uq_shipments_tenant_tracking_number"),
    )

    op.create_table(
        "shipment_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("shipment_id", sa.BigInteger(), sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("location", sa.String(length=100), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_shipment_events_shipment_occurred", "shipment_events", ["shipment_id", "occurred_at"], unique=False)

    op.create_table(
        "delivery_routes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("route_date", sa.Date(), nullable=False),
        sa.Column("vehicle_label", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("initial_distance_m", sa.Integer(), nullable=True),
        sa.Column("total_distance_m", sa.Integer(), nullable=True),
        sa.Column("iterations_run", sa.Integer(), nullable=True),
        sa.Column("optimized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "delivery_stops",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("route_id", sa.BigInteger(), sa.ForeignKey("delivery_routes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shipment_id", sa.BigInteger(), sa.ForeignKey("shipments.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("eta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("service_time_s", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("route_id", "sequence", name="uq_delivery_stops_route_sequence"),
        sa.UniqueConstraint("shipment_id", name="uq_delivery_stops_shipment"),
    )
    op.create_index("ix_delivery_stops_route_id", "delivery_stops", ["route_id"], unique=False)

    op.create_table(
        "bin_locations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("warehouse_id", sa.BigInteger(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("aisle", sa.String(length=4), nullable=False),
        sa.Column("rack", sa.SmallInteger(), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("x_m", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("y_m", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("warehouse_id", "aisle", "rack", "level", "position", name="uq_bin_locations_warehouse_coordinates"),
    )

    op.create_table(
        "slot_assignments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("bin_id", sa.BigInteger(), sa.ForeignKey("bin_locations.id"), nullable=False),
        sa.Column("pick_frequency_30d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "slotting_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("strategy", sa.String(length=20), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("bins_considered", sa.Integer(), nullable=True),
        sa.Column("avg_pick_distance_before_m", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("avg_pick_distance_after_m", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "scoring_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("params", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("workers", sa.SmallInteger(), nullable=False, server_default="4"),
        sa.Column("chunk_size", sa.Integer(), nullable=True),
        sa.Column("rows_in", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("rows_out", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "demand_scores",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("job_id", sa.BigInteger(), sa.ForeignKey("scoring_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), sa.ForeignKey("warehouses.id"), nullable=True),
        sa.Column("score_date", sa.Date(), nullable=False),
        sa.Column("predicted_units", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("model_version", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_demand_scores_job_id", "demand_scores", ["job_id"], unique=False)
    op.create_index("ix_demand_scores_tenant_product_date", "demand_scores", ["tenant_id", "product_id", "score_date"], unique=False)

    op.create_table(
        "daily_sales_summaries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("orders_count", sa.Integer(), nullable=False),
        sa.Column("items_count", sa.Integer(), nullable=False),
        sa.Column("gross_cents", sa.BigInteger(), nullable=False),
        sa.Column("discount_cents", sa.BigInteger(), nullable=False),
        sa.Column("tax_cents", sa.BigInteger(), nullable=False),
        sa.Column("net_cents", sa.BigInteger(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "summary_date", "currency", name="uq_daily_sales_summary"),
    )

    op.create_table(
        "report_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("report_type", sa.String(length=30), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "report_rows",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), sa.ForeignKey("report_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_key", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("orders_count", sa.Integer(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("revenue_cents", sa.BigInteger(), nullable=False),
        sa.Column("discount_cents", sa.BigInteger(), nullable=False),
        sa.Column("tax_cents", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_report_rows_run_id", "report_rows", ["run_id"], unique=False)

    op.create_table(
        "metric_counters",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("labels_hash", sa.CHAR(length=32), nullable=False),
        sa.Column("value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", "labels_hash", name="uq_metric_counters_tenant_name_hash"),
    )

    op.create_table(
        "export_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("export_type", sa.String(length=20), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("compressed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("signed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.CHAR(length=64), nullable=True),
        sa.Column("hmac_signature", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("export_jobs")
    op.drop_table("metric_counters")
    op.drop_table("report_rows")
    op.drop_table("report_runs")
    op.drop_table("daily_sales_summaries")
    op.drop_table("demand_scores")
    op.drop_table("scoring_jobs")
    op.drop_table("slotting_runs")
    op.drop_table("slot_assignments")
    op.drop_table("bin_locations")
    op.drop_table("delivery_stops")
    op.drop_table("delivery_routes")
    op.drop_table("shipment_events")
    op.drop_table("shipments")
    op.drop_table("tax_rules")
    op.drop_table("price_quotes")
    op.drop_table("bundle_discounts")
    op.drop_table("bundle_items")
    op.drop_table("bundles")
    op.drop_table("discounts")
    op.drop_table("product_tags")
    op.drop_table("search_terms")
    op.drop_table("stock_levels")
    op.drop_table("products")
    op.drop_table("categories")
    op.drop_table("warehouses")
    op.drop_table("fraud_checks")
    op.drop_table("blocklist_entries")
    op.drop_table("import_rows")
    op.drop_table("import_jobs")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("addresses")
    op.drop_table("customers")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("tenants")
