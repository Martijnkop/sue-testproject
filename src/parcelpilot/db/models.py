from __future__ import annotations

import datetime as dt
from enum import Enum

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from parcelpilot.db.base import Base


class TenantPlan(str, Enum):
    free = "free"
    standard = "standard"
    enterprise = "enterprise"


class UserRole(str, Enum):
    admin = "admin"
    ops = "ops"
    analyst = "analyst"
    viewer = "viewer"


class OrderStatus(str, Enum):
    pending = "pending"
    fraud_review = "fraud_review"
    confirmed = "confirmed"
    picking = "picking"
    shipped = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"


class OrderSource(str, Enum):
    api = "api"
    bulk_import = "bulk_import"


class FraudDecision(str, Enum):
    allow = "allow"
    review = "review"
    block = "block"


class BlocklistEntryType(str, Enum):
    email = "email"
    ip = "ip"
    address = "address"
    name = "name"
    phone = "phone"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    normalizing = "normalizing"


class ImportFormat(str, Enum):
    csv = "csv"
    ndjson = "ndjson"


class ImportRowStatus(str, Enum):
    pending = "pending"
    imported = "imported"
    failed = "failed"
    skipped = "skipped"


class DiscountKind(str, Enum):
    percent = "percent"
    fixed = "fixed"
    shipping = "shipping"


class ShipmentStatus(str, Enum):
    created = "created"
    in_transit = "in_transit"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    exception = "exception"
    returned = "returned"


class ShipmentEventType(str, Enum):
    picked = "picked"
    packed = "packed"
    departed = "departed"
    arrived = "arrived"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    exception = "exception"


class RouteStatus(str, Enum):
    draft = "draft"
    optimized = "optimized"
    dispatched = "dispatched"
    completed = "completed"


class SlottingStrategy(str, Enum):
    frequency_proximity = "frequency_proximity"
    affinity = "affinity"


class ExportType(str, Enum):
    orders = "orders"
    shipments = "shipments"
    stock = "stock"
    fraud_checks = "fraud_checks"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    plan: Mapped[TenantPlan] = mapped_column(SAEnum(TenantPlan, name="tenant_plan"), nullable=False, default=TenantPlan.standard)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="tenant")
    customers: Mapped[list["Customer"]] = relationship(back_populates="tenant")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        Index("ix_users_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole, name="user_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="users")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_customers_tenant_email"),
        UniqueConstraint("tenant_id", "external_ref", name="uq_customers_tenant_external_ref"),
        Index("ix_customers_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="customers")
    addresses: Mapped[list["Address"]] = relationship(back_populates="customer")
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("customers.id"), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    line1: Mapped[str] = mapped_column(String(200), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    normalized_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    customer: Mapped[Customer | None] = relationship(back_populates="addresses")
    shipping_orders: Mapped[list["Order"]] = relationship(back_populates="shipping_address")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_ref", name="uq_orders_tenant_external_ref"),
        Index("ix_orders_tenant_status", "tenant_id", "status"),
        Index("ix_orders_tenant_placed_at", "tenant_id", "status", "placed_at"),
        Index("ix_orders_customer_id", "customer_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("customers.id"), nullable=False)
    shipping_address_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("addresses.id"), nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[OrderSource] = mapped_column(SAEnum(OrderSource, name="order_source"), nullable=False, default=OrderSource.api)
    status: Mapped[OrderStatus] = mapped_column(SAEnum(OrderStatus, name="order_status"), nullable=False, default=OrderStatus.pending)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    subtotal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tax_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    shipping_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fraud_decision: Mapped[FraudDecision | None] = mapped_column(SAEnum(FraudDecision, name="fraud_decision"), nullable=True)
    fraud_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    placed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    customer: Mapped[Customer] = relationship(back_populates="orders")
    shipping_address: Mapped[Address] = relationship(back_populates="shipping_orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        Index("ix_order_items_order_id", "order_id"),
        Index("ix_order_items_product_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tax_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    line_total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    normalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    order: Mapped[Order] = relationship(back_populates="items")


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[ImportFormat] = mapped_column(SAEnum(ImportFormat, name="import_format"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JobStatus.queued.value)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orders_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ImportRow(Base):
    __tablename__ = "import_rows"
    __table_args__ = (
        UniqueConstraint("job_id", "row_number", name="uq_import_rows_job_row_number"),
        Index("ix_import_rows_job_status", "job_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[ImportRowStatus] = mapped_column(SAEnum(ImportRowStatus, name="import_row_status"), nullable=False, default=ImportRowStatus.pending)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("orders.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BlocklistEntry(Base):
    __tablename__ = "blocklist_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "entry_type", "value", name="uq_blocklist_tenant_entry_type_value"),
        Index("ix_blocklist_entry_type_value", "entry_type", "value"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=True)
    entry_type: Mapped[BlocklistEntryType] = mapped_column(SAEnum(BlocklistEntryType, name="blocklist_entry_type"), nullable=False)
    value: Mapped[str] = mapped_column(String(320), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FraudCheck(Base):
    __tablename__ = "fraud_checks"
    __table_args__ = (Index("ix_fraud_checks_order_id", "order_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    order_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("orders.id"), nullable=True)
    input_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    decision: Mapped[FraudDecision] = mapped_column(SAEnum(FraudDecision, name="fraud_decision"), nullable=False)
    matched_entry_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),
        Index("ix_warehouses_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_categories_tenant_slug"),
        Index("ix_categories_tenant_parent", "tenant_id", "parent_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("categories.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_products_tenant_sku"),
        Index("ix_products_tenant_category", "tenant_id", "category_id"),
        Index("ix_products_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("categories.id"), nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    weight_grams: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class StockLevel(Base):
    __tablename__ = "stock_levels"
    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_id", name="uq_stock_levels_product_warehouse"),
        Index("ix_stock_levels_warehouse_id", "warehouse_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("warehouses.id"), nullable=False)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SearchTerm(Base):
    __tablename__ = "search_terms"
    __table_args__ = (
        UniqueConstraint("tenant_id", "term", name="uq_search_terms_tenant_term"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    term: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProductTag(Base):
    __tablename__ = "product_tags"
    __table_args__ = (
        UniqueConstraint("product_id", "term_id", name="uq_product_tags_product_term"),
        Index("ix_product_tags_term_id", "term_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    term_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("search_terms.id", ondelete="CASCADE"), nullable=False)
    matched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Discount(Base):
    __tablename__ = "discounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_discounts_tenant_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    kind: Mapped[DiscountKind] = mapped_column(SAEnum(DiscountKind, name="discount_kind"), nullable=False)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    min_subtotal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    stack_group: Mapped[str | None] = mapped_column(String(50), nullable=True)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    valid_from: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Bundle(Base):
    __tablename__ = "bundles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BundleItem(Base):
    __tablename__ = "bundle_items"
    __table_args__ = (UniqueConstraint("bundle_id", "product_id", name="uq_bundle_items_bundle_product"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bundle_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bundles.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BundleDiscount(Base):
    __tablename__ = "bundle_discounts"
    __table_args__ = (UniqueConstraint("bundle_id", "discount_id", name="uq_bundle_discounts_bundle_discount"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bundle_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bundles.id", ondelete="CASCADE"), nullable=False)
    discount_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("discounts.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PriceQuote(Base):
    __tablename__ = "price_quotes"
    __table_args__ = (Index("ix_price_quotes_tenant_requested_at", "tenant_id", "requested_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("customers.id"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    discount_codes: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TaxRule(Base):
    __tablename__ = "tax_rules"
    __table_args__ = (Index("ix_tax_rules_tenant_country_valid_from", "tenant_id", "country_code", "valid_from"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("categories.id"), nullable=True)
    rate_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "tracking_number", name="uq_shipments_tenant_tracking_number"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id"), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("warehouses.id"), nullable=False)
    carrier: Mapped[str] = mapped_column(String(50), nullable=False)
    tracking_number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ShipmentStatus] = mapped_column(SAEnum(ShipmentStatus, name="shipment_status"), nullable=False, default=ShipmentStatus.created)
    shipped_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ShipmentEvent(Base):
    __tablename__ = "shipment_events"
    __table_args__ = (Index("ix_shipment_events_shipment_occurred", "shipment_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shipment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[ShipmentEventType] = mapped_column(SAEnum(ShipmentEventType, name="shipment_event_type"), nullable=False)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DeliveryRoute(Base):
    __tablename__ = "delivery_routes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("warehouses.id"), nullable=False)
    route_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    vehicle_label: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[RouteStatus] = mapped_column(SAEnum(RouteStatus, name="route_status"), nullable=False, default=RouteStatus.draft)
    initial_distance_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_distance_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    iterations_run: Mapped[int | None] = mapped_column(Integer, nullable=True)
    optimized_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DeliveryStop(Base):
    __tablename__ = "delivery_stops"
    __table_args__ = (
        UniqueConstraint("route_id", "sequence", name="uq_delivery_stops_route_sequence"),
        UniqueConstraint("shipment_id", name="uq_delivery_stops_shipment"),
        Index("ix_delivery_stops_route_id", "route_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("delivery_routes.id", ondelete="CASCADE"), nullable=False)
    shipment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shipments.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    eta: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    service_time_s: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BinLocation(Base):
    __tablename__ = "bin_locations"
    __table_args__ = (
        UniqueConstraint("warehouse_id", "aisle", "rack", "level", "position", name="uq_bin_locations_warehouse_coordinates"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("warehouses.id"), nullable=False)
    aisle: Mapped[str] = mapped_column(String(4), nullable=False)
    rack: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    x_m: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    y_m: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SlotAssignment(Base):
    __tablename__ = "slot_assignments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False)
    bin_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bin_locations.id"), nullable=False)
    pick_frequency_30d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assigned_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    unassigned_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SlottingRun(Base):
    __tablename__ = "slotting_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("warehouses.id"), nullable=False)
    strategy: Mapped[SlottingStrategy] = mapped_column(SAEnum(SlottingStrategy, name="slotting_strategy"), nullable=False)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus, name="job_status"), nullable=False, default=JobStatus.queued)
    bins_considered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_pick_distance_before_m: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    avg_pick_distance_after_m: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ScoringJob(Base):
    __tablename__ = "scoring_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus, name="job_status"), nullable=False, default=JobStatus.queued)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    workers: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=4)
    chunk_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_in: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    rows_out: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DemandScore(Base):
    __tablename__ = "demand_scores"
    __table_args__ = (
        Index("ix_demand_scores_job_id", "job_id"),
        Index("ix_demand_scores_tenant_product_date", "tenant_id", "product_id", "score_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    job_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("scoring_jobs.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False)
    warehouse_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("warehouses.id"), nullable=True)
    score_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    predicted_units: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    model_version: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DailySalesSummary(Base):
    __tablename__ = "daily_sales_summaries"
    __table_args__ = (UniqueConstraint("tenant_id", "summary_date", "currency", name="uq_daily_sales_summary"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    summary_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    orders_count: Mapped[int] = mapped_column(Integer, nullable=False)
    items_count: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    net_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ReportRun(Base):
    __tablename__ = "report_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    report_type: Mapped[str] = mapped_column(String(30), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus, name="job_status"), nullable=False, default=JobStatus.queued)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ReportRow(Base):
    __tablename__ = "report_rows"
    __table_args__ = (Index("ix_report_rows_run_id", "run_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("report_runs.id", ondelete="CASCADE"), nullable=False)
    group_key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    orders_count: Mapped[int] = mapped_column(Integer, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MetricCounter(Base):
    __tablename__ = "metric_counters"
    __table_args__ = (UniqueConstraint("tenant_id", "name", "labels_hash", name="uq_metric_counters_tenant_name_hash"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    labels: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    labels_hash: Mapped[str] = mapped_column(CHAR(32), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    export_type: Mapped[ExportType] = mapped_column(SAEnum(ExportType, name="export_type"), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus, name="job_status"), nullable=False, default=JobStatus.queued)
    compressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    signed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    hmac_signature: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


__all__ = [
    "Base",
    "Tenant",
    "User",
    "RefreshToken",
    "Customer",
    "Address",
    "Order",
    "OrderItem",
    "ImportJob",
    "ImportRow",
    "BlocklistEntry",
    "FraudCheck",
    "Warehouse",
    "Category",
    "Product",
    "StockLevel",
    "SearchTerm",
    "ProductTag",
    "Discount",
    "Bundle",
    "BundleItem",
    "BundleDiscount",
    "PriceQuote",
    "TaxRule",
    "Shipment",
    "ShipmentEvent",
    "DeliveryRoute",
    "DeliveryStop",
    "BinLocation",
    "SlotAssignment",
    "SlottingRun",
    "ScoringJob",
    "DemandScore",
    "DailySalesSummary",
    "ReportRun",
    "ReportRow",
    "MetricCounter",
    "ExportJob",
    "TenantPlan",
    "UserRole",
    "OrderStatus",
    "OrderSource",
    "FraudDecision",
    "BlocklistEntryType",
    "JobStatus",
    "ImportFormat",
    "ImportRowStatus",
    "DiscountKind",
    "ShipmentStatus",
    "ShipmentEventType",
    "RouteStatus",
    "SlottingStrategy",
    "ExportType",
]
