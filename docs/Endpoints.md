# ParcelPilot API: Endpoint Specification

Draft v0.1. A FastAPI service for a mid-size online marketplace: orders, fraud screening, catalog, pricing, fulfilment, routing and analytics.

Base path: `/api/v1`

Companion file: `Models.md` (database models).

---

## Conventions

- **Auth:** `Authorization: Bearer <access_token>` on every endpoint except `GET /health`, `POST /auth/login` and `POST /auth/refresh`. The tenant is resolved from the token, never passed by the client.
- **Roles:** `admin`, `ops`, `analyst`, `viewer`. Each endpoint lists the roles allowed to call it (`any` = every authenticated role).
- **Content types:** JSON unless the endpoint says *Form* (`application/x-www-form-urlencoded`) or *Multipart* (`multipart/form-data`).
- **Money:** integers in minor units (`*_cents`) plus an ISO 4217 `currency`.
- **Timestamps:** ISO 8601 UTC, e.g. `2026-10-10T09:15:02Z`. **Dates:** `YYYY-MM-DD`.
- **Pagination:** query `limit` (default 50, max 500 unless stated) and `offset` (default 0). List responses use this envelope:

```json
{ "items": [], "total": 1234, "limit": 50, "offset": 0 }
```

- **Async jobs:** long-running work returns `202 Accepted` with a `JobAccepted` body. Poll the `status_url`.

```json
{ "job_id": 42, "job_type": "import", "status": "queued", "status_url": "/api/v1/imports/42" }
```

- **Errors:** every non-2xx response (except file downloads) uses this shape. Status codes used: 400, 401, 403, 404, 409, 413, 422, 429.

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request body failed validation",
    "details": [{ "field": "items[0].quantity", "issue": "must be greater than 0" }],
    "request_id": "req_01J9ZQ4K7M"
  }
}
```

## Shared schemas

**AddressInput**

```json
{
  "line1": "Karl-Heine-Str. 12",
  "line2": null,
  "city": "Leipzig",
  "region": "SN",
  "postal_code": "04229",
  "country_code": "DE",
  "is_default": false
}
```

**Address** (response): `AddressInput` plus:

```json
{ "id": 201, "latitude": 51.3397, "longitude": 12.3731, "normalized_at": "2026-10-10T09:15:03Z" }
```

**Enums:** see `Models.md` (`OrderStatus`, `FraudDecision`, `JobStatus`, `ShipmentStatus`, and others).

---

## Endpoint index

| # | Method | Path | Summary | Input |
|---|--------|------|---------|-------|
| 1 | GET | `/health` | Liveness and DB check | none |
| 2 | POST | `/auth/login` | Exchange credentials for tokens | Form |
| 3 | POST | `/auth/refresh` | Rotate tokens | JSON |
| 4 | POST | `/auth/logout` | Revoke a refresh token | JSON |
| 5 | GET | `/auth/me` | Current user | none |
| 6 | POST | `/auth/users` | Create a user | JSON |
| 7 | POST | `/customers` | Create a customer | JSON |
| 8 | GET | `/customers/{customer_id}` | Get a customer | path |
| 9 | POST | `/orders` | Place an order (with fraud screening) | JSON |
| 10 | GET | `/orders` | List and filter orders | query |
| 11 | GET | `/orders/{order_id}` | Get an order | path |
| 12 | PATCH | `/orders/{order_id}/status` | Change order status | JSON |
| 13 | POST | `/imports/orders` | Bulk-import orders from a file | Multipart |
| 14 | GET | `/imports/{job_id}` | Import job status | path |
| 15 | GET | `/imports/{job_id}/rows` | Staged import rows | query |
| 16 | POST | `/imports/{job_id}/normalize` | Normalize addresses and prices | JSON |
| 17 | POST | `/fraud/screen` | Screen one order or payload | JSON |
| 18 | POST | `/fraud/screen/batch` | Screen many orders | JSON |
| 19 | GET | `/fraud/blocklist` | List blocklist entries | query |
| 20 | POST | `/fraud/blocklist` | Add blocklist entries in bulk | JSON |
| 21 | DELETE | `/fraud/blocklist/{entry_id}` | Remove an entry | path |
| 22 | POST | `/catalog/categories` | Create a category | JSON |
| 23 | GET | `/catalog/categories` | Category tree | query |
| 24 | GET | `/catalog/categories/{category_id}/path` | Path from root to category | path |
| 25 | GET | `/catalog/categories/{category_id}/rollup` | Rolled-up product counts | query |
| 26 | POST | `/catalog/products` | Create a product | JSON |
| 27 | POST | `/catalog/products/bulk` | Create or update many products | JSON |
| 28 | GET | `/catalog/products` | List and search products | query |
| 29 | GET | `/catalog/products/{sku}` | Get a product with stock and tags | path |
| 30 | GET | `/catalog/stock` | List stock levels | query |
| 31 | PUT | `/catalog/stock` | Bulk set or adjust stock | JSON |
| 32 | POST | `/catalog/stock/lookup` | Look up stock for many keys | JSON |
| 33 | POST | `/catalog/search/terms` | Add search terms in bulk | JSON |
| 34 | POST | `/catalog/search/tag` | Tag products by search terms | JSON |
| 35 | POST | `/pricing/quotes` | Create a price quote | JSON |
| 36 | POST | `/pricing/quotes/batch` | Create many quotes | JSON |
| 37 | GET | `/pricing/quotes/{quote_id}` | Get a quote | path |
| 38 | POST | `/pricing/discounts` | Create discounts | JSON |
| 39 | GET | `/pricing/discounts` | List discounts | query |
| 40 | POST | `/pricing/bundles` | Create a bundle | JSON |
| 41 | POST | `/pricing/bundles/best-discount` | Best discount combination | JSON |
| 42 | POST | `/reports/sales` | Generate a sales report | JSON |
| 43 | GET | `/reports/sales/{run_id}/rows` | Report rows, sortable | query |
| 44 | POST | `/analytics/daily/compute` | Compute daily summaries | JSON |
| 45 | GET | `/analytics/daily` | Read daily summaries | query |
| 46 | POST | `/analytics/tax/estimate` | Estimate tax for many lines | JSON |
| 47 | POST | `/warehouses` | Create a warehouse | JSON |
| 48 | GET | `/warehouses` | List warehouses | query |
| 49 | POST | `/warehouses/{warehouse_id}/bins/bulk` | Create bin locations | JSON |
| 50 | POST | `/warehouses/{warehouse_id}/slotting/runs` | Start a slotting analysis | JSON |
| 51 | GET | `/warehouses/{warehouse_id}/slotting/runs/{run_id}` | Slotting run result | path |
| 52 | POST | `/routing/routes` | Create a delivery route | JSON |
| 53 | POST | `/routing/routes/{route_id}/optimize` | Optimize stop order | JSON |
| 54 | GET | `/routing/routes/{route_id}` | Get a route with stops | path |
| 55 | POST | `/scoring/jobs` | Start a demand-scoring job | JSON |
| 56 | GET | `/scoring/jobs/{job_id}` | Scoring job status | path |
| 57 | GET | `/scoring/results` | Query demand scores | query |
| 58 | POST | `/metrics/events` | Ingest metric events | JSON |
| 59 | GET | `/metrics/summary` | Counter summary | query |
| 60 | POST | `/shipments` | Create a shipment for an order | JSON |
| 61 | POST | `/shipments/events/bulk` | Ingest shipment events | JSON |
| 62 | GET | `/shipments/{shipment_id}/timeline` | Shipment event timeline | path |
| 63 | POST | `/shipments/graph/rebuild` | Rebuild the in-memory event graph | JSON |
| 64 | GET | `/shipments/graph/stats` | Graph statistics | query |
| 65 | POST | `/exports` | Start a data export | JSON |
| 66 | GET | `/exports/{export_id}` | Export status | path |
| 67 | GET | `/exports/{export_id}/download` | Download the export file | path |

---

## 1. System

### `GET /health`

Roles: none (public).

**Response `200`**

```json
{ "status": "ok", "version": "0.1.0", "uptime_s": 3721, "db": "ok" }
```

---

## 2. Auth

### `POST /auth/login`

Roles: none (public). **Form** (`application/x-www-form-urlencoded`):

- `username` (string, required): the user's email.
- `password` (string, required).
- `tenant_slug` (string, required).

**Response `200`** `TokenResponse`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "rt_9f2c41d0b7a14e",
  "token_type": "bearer",
  "expires_in": 900,
  "user": { "id": 7, "tenant_id": 3, "email": "ops@acme.example", "full_name": "Ola Ops", "role": "ops" }
}
```

Errors: `401 invalid_credentials`, `429 too_many_attempts`.

### `POST /auth/refresh`

Roles: none (public).

**Body**

```json
{ "refresh_token": "rt_9f2c41d0b7a14e" }
```

**Response `200`**

```json
{ "access_token": "eyJ...", "refresh_token": "rt_3a91e07c55d2f8", "token_type": "bearer", "expires_in": 900 }
```

### `POST /auth/logout`

Roles: any.

**Body**

```json
{ "refresh_token": "rt_3a91e07c55d2f8" }
```

**Response `204`** (no body)

### `GET /auth/me`

Roles: any.

**Response `200`** `UserResponse`

```json
{ "id": 7, "tenant_id": 3, "email": "ops@acme.example", "full_name": "Ola Ops", "role": "ops", "is_active": true, "last_login_at": "2026-10-10T08:59:41Z" }
```

### `POST /auth/users`

Roles: admin.

**Body**

```json
{ "email": "analyst@acme.example", "full_name": "Ana Lyst", "password": "S3cure-passw0rd!", "role": "analyst" }
```

**Response `201`** `UserResponse`

---

## 3. Customers

### `POST /customers`

Roles: admin, ops.

**Body**

```json
{
  "email": "mia.fischer@example.com",
  "full_name": "Mia Fischer",
  "phone": "+49 341 5550123",
  "external_ref": "CRM-88231",
  "addresses": [ { "line1": "Karl-Heine-Str. 12", "city": "Leipzig", "postal_code": "04229", "country_code": "DE", "is_default": true } ]
}
```

**Response `201`** `CustomerResponse`

```json
{
  "id": 118,
  "email": "mia.fischer@example.com",
  "full_name": "Mia Fischer",
  "phone": "+49 341 5550123",
  "external_ref": "CRM-88231",
  "addresses": [ { "id": 201, "line1": "Karl-Heine-Str. 12", "line2": null, "city": "Leipzig", "region": "SN", "postal_code": "04229", "country_code": "DE", "latitude": 51.3397, "longitude": 12.3731, "is_default": true, "normalized_at": null } ],
  "created_at": "2026-10-10T09:00:00Z"
}
```

Errors: `409 email_already_exists`.

### `GET /customers/{customer_id}`

Roles: any.

**Response `200`** `CustomerResponse` plus `"order_count": 4`.

---

## 4. Orders

### `POST /orders`

Roles: admin, ops. Synchronous: the order is created, priced, taxed and fraud-screened in one request.

**Body**

```json
{
  "customer_id": 118,
  "external_ref": "WEB-2026-0001234",
  "currency": "EUR",
  "client_ip": "203.0.113.9",
  "items": [
    { "sku": "TS-BLK-M", "quantity": 2 },
    { "sku": "MUG-WHT", "quantity": 1 }
  ],
  "shipping_address_id": 201,
  "discount_codes": ["AUTUMN10"],
  "notes": "Leave at the door"
}
```

Provide either `shipping_address_id` or an inline `shipping_address` (`AddressInput`), not both.
The default shipping charge is 495 cents; eligible shipping discounts reduce it. Tax is calculated from the matching tenant tax rule, with a 19% Germany default when no tenant rules are configured.

**Response `201`** `OrderResponse`

```json
{
  "id": 90412,
  "external_ref": "WEB-2026-0001234",
  "customer_id": 118,
  "status": "confirmed",
  "source": "api",
  "currency": "EUR",
  "items": [
    { "id": 551201, "product_id": 5500, "sku": "TS-BLK-M", "quantity": 2, "unit_price_cents": 1999, "discount_cents": 400, "tax_cents": 684, "line_total_cents": 4282 },
    { "id": 551202, "product_id": 5521, "sku": "MUG-WHT", "quantity": 1, "unit_price_cents": 850, "discount_cents": 85, "tax_cents": 145, "line_total_cents": 910 }
  ],
  "subtotal_cents": 4848,
  "discount_cents": 485,
  "tax_cents": 829,
  "shipping_cents": 495,
  "total_cents": 5687,
  "shipping_address": { "id": 201, "line1": "Karl-Heine-Str. 12", "line2": null, "city": "Leipzig", "region": "SN", "postal_code": "04229", "country_code": "DE", "latitude": 51.3397, "longitude": 12.3731, "is_default": true, "normalized_at": null },
  "fraud": { "decision": "allow", "score": 12.5 },
  "notes": "Leave at the door",
  "placed_at": "2026-10-10T09:15:02Z"
}
```

`line_total_cents = quantity * unit_price_cents - discount_cents + tax_cents`.

Errors: `404 sku_not_found`, `409 duplicate_external_ref`, `409 insufficient_stock`, `422 validation_error`.

### `GET /orders`

Roles: any. **Query:**

- `status` (repeatable, `OrderStatus`)
- `customer_id` (int)
- `source` (`api` | `bulk_import`)
- `placed_from`, `placed_to` (date)
- `min_total_cents`, `max_total_cents` (int)
- `sort` (`placed_at` | `total_cents`, prefix `-` for descending, default `-placed_at`)
- `limit`, `offset`

**Response `200`** list envelope of `OrderSummary`:

```json
{
  "items": [
    { "id": 90412, "external_ref": "WEB-2026-0001234", "customer_id": 118, "status": "confirmed", "currency": "EUR", "total_cents": 5687, "fraud_decision": "allow", "placed_at": "2026-10-10T09:15:02Z" }
  ],
  "total": 1, "limit": 50, "offset": 0
}
```

### `GET /orders/{order_id}`

Roles: any.

**Response `200`** `OrderResponse` plus:

```json
{ "shipments": [ { "id": 7301, "status": "in_transit", "carrier": "DHL", "tracking_number": "JD014600003SE" } ] }
```

### `PATCH /orders/{order_id}/status`

Roles: admin, ops.

**Body**

```json
{ "status": "cancelled", "reason": "Customer request" }
```

Allowed transitions: `pending` to `confirmed` / `fraud_review` / `cancelled`; `fraud_review` to `confirmed` / `cancelled`; `confirmed` to `picking` / `cancelled`; `picking` to `shipped` / `cancelled`; `shipped` to `delivered`.

**Response `200`** `OrderSummary`. Errors: `409 invalid_transition`.

---

## 5. Bulk imports

### `POST /imports/orders`

Roles: admin, ops. **Multipart** (`multipart/form-data`):

- `file` (file, required, max 500 MB): CSV or NDJSON.
- `format` (`csv` | `ndjson`, default `csv`)
- `dry_run` (bool, default `false`)
- `default_currency` (string, default `EUR`)
- `batch_size` (int, default 1000, max 20000)

CSV columns (one row per line item; rows sharing `external_ref` form one order):

`external_ref, customer_email, sku, quantity, unit_price, currency, ship_line1, ship_line2, ship_city, ship_region, ship_postal_code, ship_country, placed_at`

`unit_price` is a decimal string such as `"19.99"`.

**Response `202`** `JobAccepted` (`job_type: "import"`).

Errors: `413 file_too_large`, `422 unsupported_format`.

### `GET /imports/{job_id}`

Roles: any.

**Response `200`** `ImportJobResponse`

```json
{
  "id": 42,
  "status": "running",
  "source_filename": "october_orders.csv",
  "format": "csv",
  "dry_run": false,
  "total_rows": 2000000,
  "processed_rows": 734000,
  "failed_rows": 112,
  "orders_created": 301245,
  "started_at": "2026-10-10T08:00:05Z",
  "finished_at": null,
  "error_summary": null
}
```

### `GET /imports/{job_id}/rows`

Roles: any. **Query:** `status` (`ImportRowStatus`), `limit` (max 1000), `offset`.

**Response `200`** list envelope:

```json
{
  "items": [
    { "row_number": 17, "status": "failed", "error": "unknown sku: TS-RED-XXL", "order_id": null, "raw": { "external_ref": "ORD-17", "sku": "TS-RED-XXL", "quantity": "1", "unit_price": "19.99" } }
  ],
  "total": 112, "limit": 50, "offset": 0
}
```

### `POST /imports/{job_id}/normalize`

Roles: admin, ops. Cleans up the orders created by an import. The import job's status moves to `normalizing`.

**Body**

```json
{ "normalize_addresses": true, "normalize_prices": true, "only_unnormalized": true, "batch_size": 5000 }
```

**Response `202`** `JobAccepted` (`job_type: "import"`, same `job_id`).

---

## 6. Fraud screening

### `POST /fraud/screen`

Roles: admin, ops. Provide either `order_id` or an inline payload.

**Body (by order)**

```json
{ "order_id": 90412 }
```

**Body (inline)**

```json
{
  "email": "mia.fischer@example.com",
  "ip_address": "203.0.113.9",
  "full_name": "Mia Fischer",
  "phone": "+49 341 5550123",
  "shipping_address": { "line1": "Karl-Heine-Str. 12", "city": "Leipzig", "postal_code": "04229", "country_code": "DE" }
}
```

**Response `200`** `FraudResult`

```json
{
  "check_id": 5531,
  "order_id": 90412,
  "decision": "review",
  "score": 61.0,
  "matches": [ { "entry_id": 17, "entry_type": "ip", "value": "203.0.113.9", "reason": "chargeback ring" } ],
  "duration_ms": 4
}
```

### `POST /fraud/screen/batch`

Roles: admin, ops.

**Body** (max 5000 ids)

```json
{ "order_ids": [90412, 90413, 90414] }
```

**Response `200`**

```json
{
  "results": [
    { "order_id": 90412, "decision": "allow", "score": 12.5, "match_count": 0 },
    { "order_id": 90413, "decision": "block", "score": 97.0, "match_count": 2 }
  ],
  "duration_ms": 31
}
```

### `GET /fraud/blocklist`

Roles: admin, ops, analyst. **Query:**

- `entry_type` (`BlocklistEntryType`)
- `q` (substring match on value)
- `include_expired` (bool, default `false`)
- `limit`, `offset`

**Response `200`** list envelope:

```json
{
  "items": [
    { "id": 17, "entry_type": "ip", "value": "203.0.113.9", "reason": "chargeback ring", "source": "manual", "scope": "tenant", "expires_at": null, "created_at": "2026-09-01T10:00:00Z" }
  ],
  "total": 100000, "limit": 50, "offset": 0
}
```

`scope` is `global` (shared across tenants) or `tenant`.

### `POST /fraud/blocklist`

Roles: admin.

**Body** (max 10000 entries)

```json
{
  "entries": [
    { "entry_type": "email", "value": "fraudster@example.net", "reason": "stolen card", "expires_at": null },
    { "entry_type": "ip", "value": "198.51.100.7", "reason": "bot traffic", "expires_at": "2027-01-01T00:00:00Z" }
  ]
}
```

**Response `201`**

```json
{ "created": 2, "skipped_duplicates": 0 }
```

### `DELETE /fraud/blocklist/{entry_id}`

Roles: admin. **Response `204`** (no body).

---

## 7. Catalog

### `POST /catalog/categories`

Roles: admin, ops.

**Body**

```json
{ "name": "Mugs", "slug": "mugs", "parent_id": 9, "sort_order": 10 }
```

**Response `201`**

```json
{ "id": 57, "parent_id": 9, "name": "Mugs", "slug": "mugs", "depth": 3, "sort_order": 10 }
```

### `GET /catalog/categories`

Roles: any. **Query:**

- `parent_id` (int, default: roots)
- `max_depth` (int, default 10)
- `tree` (bool, default `true`; `false` returns a flat list)

**Response `200`**

```json
{
  "items": [
    {
      "id": 1, "name": "Home", "slug": "home", "depth": 0, "product_count": 0,
      "children": [
        { "id": 9, "name": "Kitchen", "slug": "kitchen", "depth": 1, "product_count": 14, "children": [] }
      ]
    }
  ]
}
```

### `GET /catalog/categories/{category_id}/path`

Roles: any. Path from the root down to this category.

**Response `200`**

```json
{
  "category_id": 57,
  "depth": 3,
  "path": [
    { "id": 1, "name": "Home", "slug": "home" },
    { "id": 9, "name": "Kitchen", "slug": "kitchen" },
    { "id": 31, "name": "Tableware", "slug": "tableware" },
    { "id": 57, "name": "Mugs", "slug": "mugs" }
  ]
}
```

### `GET /catalog/categories/{category_id}/rollup`

Roles: any. **Query:** `include_inactive` (bool, default `false`).

**Response `200`**

```json
{
  "category_id": 31,
  "direct_product_count": 14,
  "total_product_count": 212,
  "by_child": [ { "category_id": 57, "name": "Mugs", "total_product_count": 40 } ]
}
```

### `POST /catalog/products`

Roles: admin, ops.

**Body**

```json
{
  "sku": "MUG-WHT",
  "name": "White Mug 350ml",
  "description": "Ceramic mug, dishwasher safe.",
  "category_id": 57,
  "base_price_cents": 850,
  "currency": "EUR",
  "weight_grams": 380,
  "attributes": { "color": "white", "capacity_ml": 350 }
}
```

**Response `201`** `ProductResponse`

```json
{
  "id": 5521, "sku": "MUG-WHT", "name": "White Mug 350ml", "description": "Ceramic mug, dishwasher safe.",
  "category_id": 57, "base_price_cents": 850, "currency": "EUR", "weight_grams": 380,
  "is_active": true, "attributes": { "color": "white", "capacity_ml": 350 }, "created_at": "2026-10-10T09:00:00Z"
}
```

Errors: `409 sku_already_exists`.

### `POST /catalog/products/bulk`

Roles: admin, ops. **Query:** `on_conflict` (`skip` | `update`, default `skip`).

**Body** (max 5000 products, each shaped like the single-create body)

```json
{ "products": [ { "sku": "MUG-BLK", "name": "Black Mug 350ml", "category_id": 57, "base_price_cents": 850, "currency": "EUR", "weight_grams": 380 } ] }
```

**Response `201`**

```json
{ "created": 4980, "updated": 0, "skipped": 20, "errors": [ { "index": 12, "sku": "MUG-XYZ", "error": "unknown category_id" } ] }
```

### `GET /catalog/products`

Roles: any. **Query:**

- `q` (text search on name and description)
- `category_id` (int) and `include_subcategories` (bool, default `true`)
- `is_active` (bool)
- `sku_prefix` (string)
- `tag` (string)
- `limit`, `offset`

**Response `200`** list envelope of `ProductResponse`.

### `GET /catalog/products/{sku}`

Roles: any.

**Response `200`** `ProductResponse` plus:

```json
{
  "tags": ["ceramic", "gift"],
  "stock": [ { "warehouse_code": "HAM", "on_hand": 120, "reserved": 4 }, { "warehouse_code": "LYS", "on_hand": 35, "reserved": 0 } ]
}
```

### `GET /catalog/stock`

Roles: any. **Query:**

- `warehouse_code` (string)
- `sku` (exact) or `sku_prefix`
- `low_stock_below` (int, matches `available` below the value)
- `limit`, `offset`

**Response `200`** list envelope:

```json
{
  "items": [ { "warehouse_code": "HAM", "sku": "MUG-WHT", "on_hand": 120, "reserved": 4, "available": 116, "updated_at": "2026-10-10T08:30:00Z" } ],
  "total": 1, "limit": 50, "offset": 0
}
```

### `PUT /catalog/stock`

Roles: admin, ops.

**Body** (max 10000 updates). `mode` is `set` (absolute) or `delta` (add or subtract).

```json
{
  "mode": "delta",
  "updates": [
    { "warehouse_code": "HAM", "sku": "MUG-WHT", "quantity": -3 },
    { "warehouse_code": "LYS", "sku": "TS-BLK-M", "quantity": 40 }
  ]
}
```

**Response `200`**

```json
{ "applied": 2, "rejected": [] }
```

### `POST /catalog/stock/lookup`

Roles: any.

**Body** (max 50000 keys)

```json
{ "keys": [ { "warehouse_code": "HAM", "sku": "MUG-WHT" }, { "warehouse_code": "LYS", "sku": "NOPE-1" } ] }
```

**Response `200`**

```json
{
  "results": [
    { "warehouse_code": "HAM", "sku": "MUG-WHT", "available": 116 },
    { "warehouse_code": "LYS", "sku": "NOPE-1", "available": null }
  ],
  "missing": 1
}
```

### `POST /catalog/search/terms`

Roles: admin, ops.

**Body** (max 10000 terms)

```json
{ "terms": ["ceramic", "dishwasher safe", "gift", "organic cotton"] }
```

**Response `201`**

```json
{ "created": 4, "existing": 0 }
```

### `POST /catalog/search/tag`

Roles: admin, ops. Scans product text for search terms and records matches as tags.

**Body**

```json
{
  "terms": null,
  "product_ids": null,
  "match_mode": "whole_word",
  "case_sensitive": false,
  "fields": ["name", "description"],
  "replace_existing": false
}
```

`terms: null` means all active search terms; `product_ids: null` means all active products.

**Response `200`**

```json
{ "products_scanned": 48210, "terms_used": 5000, "tags_created": 91234, "duration_ms": 18422 }
```

---

## 8. Pricing

### `POST /pricing/quotes`

Roles: admin, ops, analyst.

**Body**

```json
{
  "sku": "MUG-WHT",
  "quantity": 3,
  "customer_id": 118,
  "currency": "EUR",
  "requested_at": "2026-10-10T09:15:02.481Z",
  "discount_codes": ["AUTUMN10"]
}
```

`requested_at` is optional (defaults to server time) and records when the customer saw the price.

**Response `201`** `QuoteResponse`

```json
{
  "quote_id": 880122,
  "sku": "MUG-WHT",
  "quantity": 3,
  "currency": "EUR",
  "unit_price_cents": 850,
  "discount_cents": 255,
  "total_cents": 2295,
  "requested_at": "2026-10-10T09:15:02.481Z",
  "expires_at": "2026-10-10T09:45:02Z",
  "cache_hit": false
}
```

### `POST /pricing/quotes/batch`

Roles: admin, ops, analyst.

**Body** (max 1000 requests, each shaped like the single-quote body)

```json
{ "requests": [ { "sku": "MUG-WHT", "quantity": 3, "currency": "EUR" }, { "sku": "TS-BLK-M", "quantity": 1, "currency": "EUR" } ] }
```

**Response `201`**

```json
{ "quotes": [ { "quote_id": 880123, "sku": "MUG-WHT", "total_cents": 2550, "cache_hit": false } ] }
```

Each entry is a full `QuoteResponse`.

### `GET /pricing/quotes/{quote_id}`

Roles: any. **Response `200`** `QuoteResponse`.

### `POST /pricing/discounts`

Roles: admin.

**Body**

```json
{
  "discounts": [
    { "code": "AUTUMN10", "kind": "percent", "value": 1000, "min_subtotal_cents": 0, "stack_group": null, "max_uses": null, "valid_from": "2026-10-01T00:00:00Z", "valid_to": "2026-11-01T00:00:00Z" },
    { "code": "SAVE5", "kind": "fixed", "value": 500, "min_subtotal_cents": 3000, "stack_group": "cart", "max_uses": 1000, "valid_from": null, "valid_to": null }
  ]
}
```

`value` is basis points for `percent` (1000 = 10%) and cents for `fixed` and `shipping`.

**Response `201`**

```json
{ "created": 2 }
```

### `GET /pricing/discounts`

Roles: any. **Query:** `is_active` (bool), `valid_on` (date), `limit`, `offset`.

**Response `200`** list envelope:

```json
{
  "items": [ { "id": 1, "code": "AUTUMN10", "kind": "percent", "value": 1000, "min_subtotal_cents": 0, "stack_group": null, "max_uses": null, "used_count": 212, "is_active": true, "valid_from": "2026-10-01T00:00:00Z", "valid_to": "2026-11-01T00:00:00Z" } ],
  "total": 1, "limit": 50, "offset": 0
}
```

### `POST /pricing/bundles`

Roles: admin, ops.

**Body**

```json
{
  "name": "Breakfast set",
  "items": [ { "sku": "MUG-WHT", "quantity": 2 }, { "sku": "PLATE-WHT", "quantity": 2 } ],
  "discount_ids": [1, 2, 3, 4, 5, 6, 7, 8]
}
```

**Response `201`**

```json
{ "id": 12, "name": "Breakfast set", "is_active": true, "items": [ { "sku": "MUG-WHT", "quantity": 2 }, { "sku": "PLATE-WHT", "quantity": 2 } ], "discount_ids": [1, 2, 3, 4, 5, 6, 7, 8] }
```

### `POST /pricing/bundles/best-discount`

Roles: any. Finds the discount combination that saves the most, respecting stacking groups and minimum subtotals.

**Body**

```json
{ "bundle_id": 12, "candidate_discount_ids": null, "max_stacked": 6 }
```

Alternatively provide `items` (`[{ "sku", "quantity" }]`) instead of `bundle_id`. `candidate_discount_ids: null` means all discounts linked to the bundle.

**Response `200`**

```json
{
  "subtotal_cents": 3100,
  "best_combination": [
    { "discount_id": 1, "code": "AUTUMN10", "savings_cents": 310 },
    { "discount_id": 4, "code": "SAVE5", "savings_cents": 500 }
  ],
  "total_savings_cents": 810,
  "final_total_cents": 2290,
  "combinations_evaluated": 256
}
```

---

## 9. Reports and analytics

### `POST /reports/sales`

Roles: admin, analyst. Synchronous.

**Body**

```json
{ "date_from": "2026-09-01", "date_to": "2026-09-30", "group_by": "product", "currency": "EUR", "top_n": 100, "min_revenue_cents": 0 }
```

`group_by` is one of `day`, `product`, `category`, `customer`.

**Response `201`**

```json
{
  "run_id": 311,
  "status": "completed",
  "row_count": 100,
  "summary": { "orders_count": 18234, "units": 40321, "revenue_cents": 98123400 },
  "created_at": "2026-10-10T09:20:00Z"
}
```

### `GET /reports/sales/{run_id}/rows`

Roles: admin, analyst. **Query:**

- `sort_by` (`revenue_cents` | `orders_count` | `units` | `label`, default `revenue_cents`)
- `order` (`asc` | `desc`, default `desc`)
- `limit`, `offset`

**Response `200`** list envelope:

```json
{
  "items": [
    { "rank": 1, "group_key": "MUG-WHT", "label": "White Mug 350ml", "orders_count": 1204, "units": 2890, "revenue_cents": 2456500, "discount_cents": 120000, "tax_cents": 392000 }
  ],
  "total": 100, "limit": 50, "offset": 0
}
```

### `POST /analytics/daily/compute`

Roles: admin, analyst. Synchronous; range limited to 366 days.

**Body**

```json
{ "date_from": "2026-01-01", "date_to": "2026-09-30", "currency": "EUR", "recompute": false }
```

**Response `200`**

```json
{ "days_computed": 273, "summaries_written": 273, "duration_ms": 5120 }
```

### `GET /analytics/daily`

Roles: any. **Query:** `date_from` (date, required), `date_to` (date, required), `currency` (default `EUR`).

**Response `200`**

```json
{
  "items": [
    { "summary_date": "2026-09-30", "currency": "EUR", "orders_count": 812, "items_count": 1904, "gross_cents": 4120000, "discount_cents": 210000, "tax_cents": 741000, "net_cents": 3169000, "computed_at": "2026-10-01T02:00:00Z" }
  ]
}
```

### `POST /analytics/tax/estimate`

Roles: any.

**Body** (max 100000 lines)

```json
{
  "country_code": "DE",
  "region": null,
  "lines": [ { "amount_cents": 3598, "category_id": 57 }, { "amount_cents": 765, "category_id": 57 } ]
}
```

**Response `200`**

```json
{
  "total_tax_cents": 829,
  "lines": [
    { "index": 0, "tax_cents": 684, "rate_bps": 1900, "rule_id": 3 },
    { "index": 1, "tax_cents": 145, "rate_bps": 1900, "rule_id": 3 }
  ]
}
```

---

## 10. Warehouses and slotting

### `POST /warehouses`

Roles: admin.

**Body**

```json
{ "code": "HAM", "name": "Hamburg Central", "city": "Hamburg", "country_code": "DE", "latitude": 53.5511, "longitude": 9.9937 }
```

**Response `201`**

```json
{ "id": 3, "code": "HAM", "name": "Hamburg Central", "city": "Hamburg", "country_code": "DE", "latitude": 53.5511, "longitude": 9.9937, "is_active": true }
```

### `GET /warehouses`

Roles: any. **Query:** `is_active` (bool), `limit`, `offset`.

**Response `200`** list envelope of the warehouse object above.

### `POST /warehouses/{warehouse_id}/bins/bulk`

Roles: admin, ops.

**Body** (max 20000 bins)

```json
{ "bins": [ { "aisle": "A", "rack": 3, "level": 2, "position": 5, "x_m": 12.5, "y_m": 4.0 } ] }
```

**Response `201`**

```json
{ "created": 5000, "skipped": 0 }
```

### `POST /warehouses/{warehouse_id}/slotting/runs`

Roles: admin, ops, analyst. Analyses pick paths across all bins to suggest better product placement.

**Body**

```json
{ "strategy": "frequency_proximity", "lookback_days": 30, "max_bins": 5000, "dry_run": true }
```

**Response `202`** `JobAccepted` (`job_type: "slotting"`, `status_url` pointing at the run).

### `GET /warehouses/{warehouse_id}/slotting/runs/{run_id}`

Roles: any.

**Response `200`**

```json
{
  "run_id": 19,
  "warehouse_id": 3,
  "strategy": "frequency_proximity",
  "status": "completed",
  "bins_considered": 5000,
  "avg_pick_distance_before_m": 41.7,
  "avg_pick_distance_after_m": 33.2,
  "result": { "moves_suggested": 212, "top_moves": [ { "sku": "MUG-WHT", "from_bin": "C-12-1-4", "to_bin": "A-01-2-1", "gain_m": 18.4 } ] },
  "started_at": "2026-10-10T09:30:00Z",
  "finished_at": "2026-10-10T09:30:41Z"
}
```

---

## 11. Routing

### `POST /routing/routes`

Roles: admin, ops. Stops are created in the order submitted; shipments must have a geocoded delivery address.

**Body**

```json
{ "warehouse_id": 3, "route_date": "2026-10-11", "vehicle_label": "VAN-07", "shipment_ids": [7301, 7302, 7303] }
```

**Response `201`** `RouteResponse` (see below) with `status: "draft"`.

### `POST /routing/routes/{route_id}/optimize`

Roles: admin, ops. Improves stop ordering with a local-search heuristic. Synchronous.

**Body**

```json
{ "algorithm": "two_opt", "max_iterations": 10000, "time_limit_ms": 5000 }
```

**Response `200`**

```json
{
  "route_id": 88,
  "initial_distance_m": 184200,
  "optimized_distance_m": 151900,
  "improvement_pct": 17.5,
  "iterations_run": 9120,
  "duration_ms": 4310
}
```

### `GET /routing/routes/{route_id}`

Roles: any.

**Response `200`** `RouteResponse`

```json
{
  "id": 88,
  "warehouse_id": 3,
  "route_date": "2026-10-11",
  "vehicle_label": "VAN-07",
  "status": "optimized",
  "total_distance_m": 151900,
  "stops": [
    { "sequence": 1, "shipment_id": 7302, "latitude": 53.5753, "longitude": 10.0153, "eta": "2026-10-11T08:20:00Z", "service_time_s": 120 },
    { "sequence": 2, "shipment_id": 7301, "latitude": 53.5461, "longitude": 9.9663, "eta": "2026-10-11T08:41:00Z", "service_time_s": 120 }
  ]
}
```

---

## 12. Demand scoring

### `POST /scoring/jobs`

Roles: admin, analyst.

**Body**

```json
{ "product_ids": null, "warehouse_ids": null, "horizon_days": 14, "lookback_days": 180, "workers": 4, "chunk_size": null }
```

`null` for `product_ids` / `warehouse_ids` means all. `chunk_size: null` lets the service decide.

**Response `202`** `JobAccepted` (`job_type: "scoring"`).

### `GET /scoring/jobs/{job_id}`

Roles: any.

**Response `200`**

```json
{
  "id": 27,
  "status": "running",
  "params": { "horizon_days": 14, "lookback_days": 180 },
  "rows_in": 4200000,
  "rows_out": 380000,
  "workers": 4,
  "chunk_size": 50000,
  "started_at": "2026-10-10T09:40:00Z",
  "finished_at": null,
  "error": null
}
```

### `GET /scoring/results`

Roles: admin, analyst. **Query:**

- `job_id`, `product_id`, `warehouse_id` (int)
- `date_from`, `date_to` (date)
- `min_confidence` (float 0 to 1)
- `sort_by` (`predicted_units` | `confidence` | `score_date`, default `predicted_units`)
- `limit`, `offset`

**Response `200`** list envelope:

```json
{
  "items": [ { "product_id": 5521, "sku": "MUG-WHT", "warehouse_id": 3, "score_date": "2026-10-17", "predicted_units": 142.5, "confidence": 0.874, "model_version": "demand-v3" } ],
  "total": 380000, "limit": 50, "offset": 0
}
```

---

## 13. Metrics

### `POST /metrics/events`

Roles: any.

**Body** (max 10000 events)

```json
{
  "events": [
    { "name": "orders.created", "labels": { "source": "api" }, "value": 1, "timestamp": "2026-10-10T09:15:02Z" },
    { "name": "quotes.latency_ms", "labels": { "endpoint": "pricing" }, "value": 37.2, "timestamp": "2026-10-10T09:15:03Z" }
  ]
}
```

**Response `202`**

```json
{ "accepted": 2 }
```

### `GET /metrics/summary`

Roles: admin, analyst. **Query:** `name_prefix` (string), `since` (timestamp, default one hour ago).

**Response `200`**

```json
{
  "since": "2026-10-10T08:15:00Z",
  "counters": [ { "name": "orders.created", "labels": { "source": "api" }, "value": 1820, "updated_at": "2026-10-10T09:15:02Z" } ]
}
```

---

## 14. Shipments

### `POST /shipments`

Roles: admin, ops.

**Body**

```json
{ "order_id": 90412, "warehouse_code": "HAM", "carrier": "DHL" }
```

**Response `201`**

```json
{ "id": 7301, "order_id": 90412, "warehouse_code": "HAM", "carrier": "DHL", "tracking_number": "JD014600003SE", "status": "created", "created_at": "2026-10-10T09:50:00Z" }
```

### `POST /shipments/events/bulk`

Roles: admin, ops.

**Body** (max 20000 events)

```json
{
  "events": [
    { "tracking_number": "JD014600003SE", "event_type": "departed", "location": "HAM", "occurred_at": "2026-10-10T11:02:00Z", "payload": { "vehicle": "TRK-221" } }
  ]
}
```

`event_type` values: see `ShipmentEventType` in `Models.md`.

**Response `201`**

```json
{ "accepted": 1, "rejected": [] }
```

### `GET /shipments/{shipment_id}/timeline`

Roles: any.

**Response `200`**

```json
{
  "shipment_id": 7301,
  "status": "in_transit",
  "events": [
    { "event_type": "picked", "location": "HAM", "occurred_at": "2026-10-10T10:10:00Z", "payload": {} },
    { "event_type": "departed", "location": "HAM", "occurred_at": "2026-10-10T11:02:00Z", "payload": { "vehicle": "TRK-221" } }
  ]
}
```

### `POST /shipments/graph/rebuild`

Roles: admin. Loads shipment events into an in-memory graph used for transit analytics.

**Body** (all fields optional)

```json
{ "since": "2026-01-01", "status": ["created", "in_transit"] }
```

**Response `202`**

```json
{ "status": "rebuilding", "started_at": "2026-10-10T10:00:00Z" }
```

### `GET /shipments/graph/stats`

Roles: admin, analyst. **Query:** `group_by` (`event_type` | `location` | `carrier`, default `event_type`), `min_count` (int, default 1).

**Response `200`**

```json
{
  "built_at": "2026-10-10T10:03:12Z",
  "nodes": 5000000,
  "edges": 4800000,
  "groups": [ { "key": "departed", "count": 1200000, "avg_transit_hours": 18.4 } ]
}
```

Errors: `409 graph_not_built`.

---

## 15. Exports

### `POST /exports`

Roles: admin.

**Body**

```json
{ "export_type": "orders", "date_from": "2026-09-01", "date_to": "2026-09-30", "compress": true, "sign": true }
```

**Response `202`** `JobAccepted` (`job_type: "export"`, `job_id` is the export id).

### `GET /exports/{export_id}`

Roles: admin.

**Response `200`**

```json
{
  "id": 14,
  "export_type": "orders",
  "status": "completed",
  "compressed": true,
  "size_bytes": 482133990,
  "sha256": "9b74c9897bac770ffc029102a200c5de...",
  "signature": "hmac-sha256:3f1a0c...",
  "finished_at": "2026-10-10T10:20:00Z",
  "download_url": "/api/v1/exports/14/download"
}
```

### `GET /exports/{export_id}/download`

Roles: admin. Streams the file (not JSON).

**Response `200` headers**

```
Content-Type: application/gzip
Content-Disposition: attachment; filename="orders_2026-09-01_2026-09-30.ndjson.gz"
X-Signature: hmac-sha256:3f1a0c...
```

Errors (JSON): `404 export_not_found`, `409 export_not_ready`.

---

## Non-HTTP entrypoint

The CLI `parcelpilot-worker` is not part of the HTTP API. It is the entrypoint for background runs of the same jobs. Planned commands: `import-orders`, `score`, `export`, `rebuild-graph`.

---

## Test-author notes (remove before sharing with the analyzer)

Mapping of endpoints to the planted issue IDs from the pattern list. Not part of the API contract.

| Issue | Endpoint(s) |
|-------|-------------|
| H1 (property recomputes) | `POST /reports/sales`, `GET /reports/sales/{run_id}/rows` |
| H2 (hidden list membership) | `POST /fraud/screen`, `POST /fraud/screen/batch`, `POST /orders` |
| H3 (repeated serialization) | `POST /orders` |
| H4 (eager log formatting) | `POST /orders` and most write endpoints |
| H5 (bad `__hash__`) | `POST /catalog/stock/lookup`, `PUT /catalog/stock` |
| H6 (recursion with slicing) | `GET /catalog/categories`, `.../{id}/path`, `.../{id}/rollup` |
| H7 (useless cache) | `POST /pricing/quotes`, `POST /pricing/quotes/batch` |
| H8 (regex cache thrash) | `POST /catalog/search/tag` |
| H9 (`np.vectorize`) | `POST /analytics/tax/estimate` |
| H10 (growing DataFrame) | `POST /analytics/daily/compute` |
| P1 (self time in builtin) | `POST /fraud/screen` (leaf is `list.__contains__`) |
| P2 (many cheap calls) | `POST /imports/{job_id}/normalize`, `POST /imports/orders` |
| P3 (flat profile) | `POST /orders` (layered validation, logging, copies) |
| P4 (recursion, no memoization) | `POST /pricing/bundles/best-discount` |
| P5 (GC pressure) | `POST /shipments/graph/rebuild` |
| P6 (profiler-inflated helpers) | `POST /imports/{job_id}/normalize` (tiny helpers such as price conversion) |
| P7 (pickling dominates) | `POST /scoring/jobs` |
| P8 (lock contention) | `POST /metrics/events` |
| P9 (event loop blocked) | `POST /auth/login` |
| P10 (legitimately expensive) | `POST /auth/login` (bcrypt), `POST /exports` (gzip, HMAC) |
| P11 (workload-dependent) | stock lookup, search tagging and fraud screening with a hostile tenant dataset |
| P12 (needs Cython/Numba) | `POST /routing/routes/{route_id}/optimize` |
| P13 (memory layout) | `POST /warehouses/{warehouse_id}/slotting/runs` |
| P14 (startup cost) | CLI `parcelpilot-worker` |
