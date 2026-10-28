from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from parcelpilot.catalog.keys import SkuKey
from parcelpilot.catalog.stock_service import lookup_available_rows
from parcelpilot.catalog.tree import find_chain, rollup
from parcelpilot.core.pagination import normalize_pagination
from parcelpilot.warehouses.api import _WAREHOUSES

router = APIRouter(prefix="/catalog", tags=["catalog"])

_CATEGORIES: dict[int, dict[str, Any]] = {}
_CATEGORY_SEQUENCE = 0


class CategoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    slug: str
    parent_id: int | None = None
    sort_order: int = 0


def _make_category(category_id: int, payload: CategoryCreateRequest) -> dict[str, Any]:
    parent_id = payload.parent_id
    parent_depth = 0
    if parent_id is not None:
        parent = _CATEGORIES.get(parent_id)
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "category_not_found", "message": "Parent category not found"},
            )
        parent_depth = int(parent.get("depth", 0))
    return {
        "id": category_id,
        "name": payload.name,
        "slug": payload.slug,
        "parent_id": parent_id,
        "depth": parent_depth + 1 if parent_id is not None else 0,
        "sort_order": payload.sort_order,
        "product_count": 0,
        "is_active": True,
    }


def _ordered_categories() -> list[dict[str, Any]]:
    return sorted(_CATEGORIES.values(), key=lambda item: (item.get("depth", 0), item.get("sort_order", 0), item.get("id", 0)))


def _build_tree_data(categories: list[dict[str, Any]], *, parent_id: int | None = None, max_depth: int = 10) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for category in categories:
        if category.get("parent_id") != parent_id:
            continue
        if category.get("depth", 0) > max_depth:
            continue
        branch = {
            "id": category["id"],
            "name": category["name"],
            "slug": category["slug"],
            "depth": category["depth"],
            "product_count": category.get("product_count", 0),
            "children": _build_tree_data(categories, parent_id=category["id"], max_depth=max_depth),
        }
        items.append(branch)
    return items


@router.get("")
def list_catalog() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/categories")
def create_category(payload: CategoryCreateRequest) -> dict[str, Any]:
    global _CATEGORY_SEQUENCE
    _CATEGORY_SEQUENCE += 1
    category = _make_category(_CATEGORY_SEQUENCE, payload)
    _CATEGORIES[category["id"]] = category
    return {
        "id": category["id"],
        "parent_id": category["parent_id"],
        "name": category["name"],
        "slug": category["slug"],
        "depth": category["depth"],
        "sort_order": category["sort_order"],
    }


@router.get("/categories")
def list_categories(
    parent_id: int | None = Query(default=None),
    max_depth: int = Query(default=10, ge=0),
    tree: bool = Query(default=True),
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    categories = _ordered_categories()
    if parent_id is not None:
        filtered = [category for category in categories if category.get("parent_id") == parent_id]
    else:
        filtered = [category for category in categories if category.get("parent_id") is None]

    if tree:
        items = _build_tree_data(categories, parent_id=parent_id, max_depth=max_depth)
    else:
        items = [
            {
                "id": category["id"],
                "name": category["name"],
                "slug": category["slug"],
                "depth": category["depth"],
                "product_count": category.get("product_count", 0),
            }
            for category in filtered
            if category.get("depth", 0) <= max_depth
        ]

    resolved_limit, resolved_offset = normalize_pagination(limit, offset)
    page = items[resolved_offset : resolved_offset + resolved_limit]
    return {"items": page, "total": len(items), "limit": resolved_limit, "offset": resolved_offset}


@router.get("/categories/{category_id}/path")
def category_path(category_id: int) -> dict[str, Any]:
    categories = _ordered_categories()
    chain = find_chain(categories, category_id)
    if not chain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "category_not_found", "message": "Category not found"},
        )
    return {
        "category_id": category_id,
        "depth": len(chain) - 1,
        "path": [{"id": item["id"], "name": item["name"], "slug": item["slug"]} for item in chain],
    }


@router.get("/categories/{category_id}/rollup")
def category_rollup(category_id: int, include_inactive: bool = Query(default=False)) -> dict[str, Any]:
    categories = _ordered_categories()
    node = next((item for item in categories if item["id"] == category_id), None)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "category_not_found", "message": "Category not found"},
        )
    result = rollup(node, categories, include_inactive=include_inactive)
    return {
        "category_id": category_id,
        "direct_product_count": result["direct_product_count"],
        "total_product_count": result["total_product_count"],
        "by_child": result["by_child"],
    }


_PRODUCTS: dict[str, dict[str, Any]] = {}
_PRODUCT_SEQUENCE = 1
_STOCK: dict[SkuKey, dict[str, Any]] = {}


class ProductCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sku: str
    name: str
    description: str | None = None
    category_id: int
    base_price_cents: int = 0
    currency: str = "EUR"
    weight_grams: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True


class ProductBulkPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    products: list[ProductCreateRequest] = Field(default_factory=list)


class StockUpdateItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    warehouse_code: str
    sku: str
    quantity: int


class StockUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: str = "delta"
    updates: list[StockUpdateItem] = Field(default_factory=list)


class StockLookupRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    keys: list[dict[str, str]] = Field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_category(category_id: int) -> dict[str, Any]:
    category = _CATEGORIES.get(category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "category_not_found", "message": "Category not found"},
        )
    return category


def _category_subtree_ids(category_id: int) -> set[int]:
    result = {category_id}
    pending = [category_id]
    while pending:
        current = pending.pop()
        for item in _CATEGORIES.values():
            if item.get("parent_id") == current and item["id"] not in result:
                result.add(item["id"])
                pending.append(item["id"])
    return result


def _serialize_product(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": product["id"],
        "sku": product["sku"],
        "name": product["name"],
        "description": product.get("description"),
        "category_id": product["category_id"],
        "base_price_cents": product.get("base_price_cents", 0),
        "currency": product.get("currency", "EUR"),
        "weight_grams": product.get("weight_grams"),
        "is_active": product.get("is_active", True),
        "attributes": product.get("attributes", {}),
        "created_at": product["created_at"],
    }


def _stock_available(row: dict[str, Any]) -> int:
    return int(row.get("on_hand", 0)) - int(row.get("reserved", 0))


def _product_count_for_categories(category_ids: set[int]) -> list[dict[str, Any]]:
    return [
        product
        for product in _PRODUCTS.values()
        if product.get("category_id") in category_ids and product.get("is_active", True)
    ]


@router.post("/products")
def create_product(payload: ProductCreateRequest) -> dict[str, Any]:
    sku = payload.sku.strip().upper()
    if sku in _PRODUCTS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "sku_already_exists", "message": "Product SKU already exists"},
        )

    _resolve_category(payload.category_id)
    product_id = max((int(product["id"]) for product in _PRODUCTS.values()), default=0) + 1
    product = {
        "id": product_id,
        "sku": sku,
        "name": payload.name,
        "description": payload.description,
        "category_id": payload.category_id,
        "base_price_cents": payload.base_price_cents,
        "currency": payload.currency,
        "weight_grams": payload.weight_grams,
        "is_active": payload.is_active,
        "attributes": payload.attributes,
        "created_at": _now_iso(),
        "tags": list(payload.tags),
    }
    _PRODUCTS[sku] = product
    category = _resolve_category(payload.category_id)
    category["product_count"] = int(category.get("product_count", 0)) + 1
    return _serialize_product(product)


@router.post("/products/bulk")
def bulk_create_products(payload: ProductBulkPayload, on_conflict: str = Query(default="skip")) -> dict[str, Any]:
    created = 0
    updated = 0
    skipped = 0
    errors: list[dict[str, Any]] = []

    for index, item in enumerate(payload.products):
        try:
            existing = _PRODUCTS.get(item.sku.strip().upper())
            if existing is not None:
                if on_conflict == "update":
                    existing["name"] = item.name
                    existing["description"] = item.description
                    existing["category_id"] = item.category_id
                    existing["base_price_cents"] = item.base_price_cents
                    existing["currency"] = item.currency
                    existing["weight_grams"] = item.weight_grams
                    existing["attributes"] = item.attributes
                    existing["tags"] = list(item.tags)
                    updated += 1
                else:
                    skipped += 1
                    continue
            else:
                _resolve_category(item.category_id)
                product_id = max((int(product["id"]) for product in _PRODUCTS.values()), default=0) + 1
                record = {
                    "id": product_id,
                    "sku": item.sku.strip().upper(),
                    "name": item.name,
                    "description": item.description,
                    "category_id": item.category_id,
                    "base_price_cents": item.base_price_cents,
                    "currency": item.currency,
                    "weight_grams": item.weight_grams,
                    "is_active": item.is_active,
                    "attributes": item.attributes,
                    "created_at": _now_iso(),
                    "tags": list(item.tags),
                }
                _PRODUCTS[record["sku"]] = record
                category = _resolve_category(item.category_id)
                category["product_count"] = int(category.get("product_count", 0)) + 1
                created += 1
        except HTTPException as exc:
            errors.append({"index": index, "sku": item.sku, "error": exc.detail.get("message", "unknown category_id")})

    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}


@router.get("/products")
def list_products(
    q: str | None = None,
    category_id: int | None = None,
    include_subcategories: bool = Query(default=True),
    is_active: bool | None = None,
    sku_prefix: str | None = None,
    tag: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    items = list(_PRODUCTS.values())
    if q:
        needle = q.lower()
        items = [product for product in items if needle in (product.get("name", "") + " " + (product.get("description") or "")).lower()]
    if category_id is not None:
        allowed = {category_id}
        if include_subcategories:
            allowed |= _category_subtree_ids(category_id)
        items = [product for product in items if product.get("category_id") in allowed]
    if is_active is not None:
        items = [product for product in items if bool(product.get("is_active", True)) == is_active]
    if sku_prefix:
        prefix = sku_prefix.strip().upper()
        items = [product for product in items if product.get("sku", "").startswith(prefix)]
    if tag:
        tag_name = tag.strip().lower()
        items = [product for product in items if tag_name in [entry.lower() for entry in product.get("tags", [])]]

    filtered = sorted(items, key=lambda product: product["id"])
    resolved_limit, resolved_offset = normalize_pagination(limit, offset)
    page = [
        _serialize_product(product)
        for product in filtered[resolved_offset : resolved_offset + resolved_limit]
    ]
    return {"items": page, "total": len(filtered), "limit": resolved_limit, "offset": resolved_offset}


@router.get("/products/{sku}")
def get_product(sku: str) -> dict[str, Any]:
    item = _PRODUCTS.get(sku.strip().upper())
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "sku_not_found", "message": "Product not found"},
        )

    response = _serialize_product(item)
    response["tags"] = list(item.get("tags", []))
    response["stock"] = [
        {
            "warehouse_code": row["warehouse_code"],
            "on_hand": row.get("on_hand", 0),
            "reserved": row.get("reserved", 0),
        }
        for row in sorted(_STOCK.values(), key=lambda record: (record["warehouse_code"], record["sku"]))
        if row["sku"] == sku.strip().upper()
    ]
    return response


@router.get("/stock")
def list_stock(
    warehouse_code: str | None = None,
    sku: str | None = None,
    sku_prefix: str | None = None,
    low_stock_below: int | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    rows = list(_STOCK.values())
    if warehouse_code:
        rows = [row for row in rows if row["warehouse_code"].upper() == warehouse_code.strip().upper()]
    if sku:
        rows = [row for row in rows if row["sku"].upper() == sku.strip().upper()]
    if sku_prefix:
        prefix = sku_prefix.strip().upper()
        rows = [row for row in rows if row["sku"].upper().startswith(prefix)]
    if low_stock_below is not None:
        rows = [row for row in rows if _stock_available(row) < int(low_stock_below)]

    filtered = sorted(rows, key=lambda row: (row["warehouse_code"], row["sku"]))
    resolved_limit, resolved_offset = normalize_pagination(limit, offset)
    page = [{
        "warehouse_code": row["warehouse_code"],
        "sku": row["sku"],
        "on_hand": row.get("on_hand", 0),
        "reserved": row.get("reserved", 0),
        "available": _stock_available(row),
        "updated_at": row.get("updated_at"),
    } for row in filtered[resolved_offset : resolved_offset + resolved_limit]]
    return {"items": page, "total": len(filtered), "limit": resolved_limit, "offset": resolved_offset}


@router.put("/stock")
def update_stock(payload: StockUpdateRequest) -> dict[str, Any]:
    applied = 0
    rejected: list[dict[str, Any]] = []

    for update in payload.updates:
        warehouse_code = update.warehouse_code.strip().upper()
        sku = update.sku.strip().upper()
        if warehouse_code not in {entry["code"] for entry in _WAREHOUSES.values()}:
            rejected.append({"warehouse_code": warehouse_code, "sku": sku, "error": "unknown warehouse_code"})
            continue
        if sku not in _PRODUCTS:
            rejected.append({"warehouse_code": warehouse_code, "sku": sku, "error": "unknown sku"})
            continue
        key = SkuKey(warehouse_code, sku)
        row = _STOCK.get(key)
        if row is None:
            row = {
                "warehouse_code": warehouse_code,
                "sku": sku,
                "on_hand": 0,
                "reserved": 0,
                "updated_at": _now_iso(),
            }
        if payload.mode == "set":
            row["on_hand"] = int(update.quantity)
        else:
            row["on_hand"] = int(row.get("on_hand", 0)) + int(update.quantity)
        row["updated_at"] = _now_iso()
        _STOCK[key] = row
        applied += 1

    return {"applied": applied, "rejected": rejected}


@router.post("/stock/lookup")
def lookup_stock(payload: StockLookupRequest) -> dict[str, Any]:
    results, missing = lookup_available_rows(
        [dict(row) for row in _STOCK.values()],
        [dict(item) for item in payload.keys],
    )
    return {"results": results, "missing": missing}
