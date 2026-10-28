# ParcelPilot: Build Plan (todo.md)

Order of work for building the ParcelPilot test application: a FastAPI service that carries deliberately CPU-unoptimized code so an AI-driven CI pipeline (flamegraphs, `self_time`, `total_time`) can be tested against it.

Companion files: `Endpoints.md` (API contract), `Models.md` (database models), `cpu_antipatterns.md` (issue catalogue, IDs **H1-H10** and **P1-P14**).

---

## How to read this file

- **Grouped by MoSCoW**, then numbered in build order (`T01`, `T02`, ...). Numbers only go up across groups, so Must comes first, then Should, Could, Won't.
- **Dependency rule:** an item only depends on items with a lower number. No Must item depends on a Should or Could item.
- **Size:** S = up to half a day, M = 1-2 days, L = 3+ days. These are rough.
- **Malpractice** = the deliberate CPU problem planted in that item. "Control" = the code must be written *well*, so the analyzer has clean code to leave alone.
- **Design note** = a decision carried over from the earlier design discussion, placed where it applies.

### Standard definition of done for an issue item (DoD-I)

Every item that plants a malpractice is only done when all of these hold. Items below list only the extras.

1. The malpractice exists in the files named in the item, and the endpoint still returns correct results.
2. **Oracle:** golden outputs recorded from the unoptimized code on fixed inputs, including the edge cases listed in the item, and passing.
3. **Tripwire:** a test that fails if someone accidentally "fixes" the malpractice (call counts, cache hit counts, growth-ratio checks).
4. **Benchmark:** baseline recorded, plus the speedup an optimized version should reach (stored in the manifest).
5. **Manifest entry** in `ground_truth/issues.yaml` (see T09).
6. **Expected-signal entry** in `ground_truth/expected_signals.yaml` (see T26).
7. Hint-hygiene test passes (no comments or names that reveal the issue).
8. The endpoint is covered by a scenario in the profiling harness (T25 or T37).

---

## Overview

### Must

| ID | Item | Size | Depends on | Issues planted |
|----|------|------|-----------|----------------|
| T01 | Repo scaffold, tooling, layout | S | none | none |
| T02 | Local infra and settings | S | T01 | none |
| T03 | Database models and migrations | M | T01, T02 | none |
| T04 | App skeleton and conventions (`/health`) | M | T03 | none |
| T05 | Seed bootstrap endpoints | S | T03, T04 | none |
| T06 | Workload definitions (benign, typical, hostile) | S | T03 | none |
| T07 | Seed generators and workload seeding endpoints | L | T05, T06 | none |
| T08 | Test infrastructure (oracle, tripwire, benchmark) | M | T04, T07 | none |
| T09 | Ground-truth manifest and hint hygiene | S | T01 | none |
| T10 | Auth | M | T04, T05, T08, T09 | P9, P10 |
| T11 | Customers | S | T10 | control |
| T12 | Warehouses | S | T10 | control |
| T13 | Catalog categories | M | T10 | H6 |
| T14 | Products and stock | L | T12, T13 | H5, P11 |
| T15 | Discounts, quotes, pricing/tax services | M | T14 | H7 |
| T16 | Bundles and best discount | M | T14, T15 | P4 |
| T17 | Fraud screening and blocklist | M | T07, T10 | H2, P1 |
| T18 | Orders | L | T11, T15, T17 | H3, H4, P3 |
| T19 | Bulk imports and normalization | L | T11, T14, T18 | P2, P6 |
| T20 | Sales reports | M | T18 | H1 |
| T21 | Daily analytics | M | T18 | H10 |
| T22 | Tax estimate | S | T13, T15 | H9 |
| T23 | Decision: profile artifact format | S | none | none |
| T24 | Profile harness core | L | T07, T23 | none |
| T25 | Human-like scenarios (Must endpoints) | L | T24, T10-T22 | none |
| T26 | Expected-signal validation | M | T09, T25 | none |
| T27 | Dev entrypoints, docs, app CI | S | T08, T26 | none |

### Should

| ID | Item | Size | Depends on | Issues planted |
|----|------|------|-----------|----------------|
| T28 | Seed extensions (shipments, events, bins, demand history) | M | T07 | none |
| T29 | Shipments and event graph | L | T18, T28 | P5 |
| T30 | Routing | M | T29 | P12 |
| T31 | Warehouse bins and slotting | M | T12, T18, T28 | P13 |
| T32 | Search terms and tagging | M | T07, T14 | H8 |
| T33 | Extra capture modes (subprocess, GIL, idle) | M | T24 | none |
| T34 | Demand scoring | L | T18, T28, T33 | P7 |
| T35 | Metrics | M | T10, T33 | P8 |
| T36 | Exports | M | T18, T29 | P10 (restraint) |
| T37 | Scenarios for Should endpoints | M | T25, T29-T36 | none |
| T38 | Reference fixes and speedup tests | L | T36 | none |
| T39 | Containerized app and profiling | S | T24 | none |
| T40 | Analyzer-view packaging and leak check | S | T09, T36 | none |

### Could

| ID | Item | Size | Depends on | Issues planted |
|----|------|------|-----------|----------------|
| T41 | CLI worker and startup profile | M | T19, T29, T34, T36 | P14 |
| T42 | Pre-recorded profile fixtures and synthetic hard cases | M | T26, T37 | none |
| T43 | Profile diff tool and benchmark history | M | T26 | none |
| T44 | Marginal-gain traps and extra controls | S | T18, T19 | trap spots |
| T45 | Bonus patterns from the first list (feature-flagged) | M | T19 | extras |
| T46 | Fix-interaction tests | S | T08, T15, T29 | none |
| T47 | Nightly full-scale run | S | T27, T37 | none |

### Won't (this iteration)

See the end of the file.

---

# MUST

## Phase A: Foundations

### T01: Repo scaffold, tooling and layout
**Size:** S | **Depends on:** none

**Build**
- Python 3.12, `pyproject.toml`, lockfile with **exact pinned versions**.
- Runtime deps: fastapi, uvicorn, pydantic v2, pydantic-settings, SQLAlchemy 2.0, psycopg 3, Alembic, bcrypt, PyJWT, numpy, pandas, python-multipart.
- Dev deps: pytest, pytest-asyncio, pytest-benchmark, httpx, locust, py-spy, ruff, faker.
- Ruff in **format-only plus basic correctness rules**. Turn off the perf-oriented families (`PERF`, `C4`, `SIM`) because they would flag the planted issues and quietly fix them.
- Repository layout:

```
parcelpilot/
  main.py  settings.py
  core/        logging, errors, pagination, security, deps
  db/          models, session
  config/      lists.py (loaded blocklists)
  auth/ customers/ warehouses/ catalog/ pricing/ fraud/ orders/ imports/
  reports/ analytics/ shipments/ routing/ slotting/ scoring/ metrics/ exports/
     (each module: api.py, service.py, repo.py, plus module-specific files)
  dev/         seed endpoints and generators (excluded from analysis)
  cli/
profiling/     run.py, capture.py, scenarios/, validate.py
tests/         unit/ api/ oracles/ bench/ e2e/ seed/
ground_truth/  issues.yaml, expected_signals.yaml
reference_fixes/
scripts/  docs/
```

**Design notes**
- *Pin everything.* Profiles must be reproducible between runs; versions are recorded in every profile's `meta.json`.
- *Module-per-domain with `api` / `service` / `repo` files.* This is what makes cross-file issues (H1, H2, H3) realistic: the cost lives in one file and is triggered from another.

**Done when:** `make check` runs lint and an empty test suite on a fresh clone.

---

### T02: Local infra and settings
**Size:** S | **Depends on:** T01

**Build**
- `docker-compose.yml` with PostgreSQL 16 and a health check.
- `settings.py` (pydantic-settings), env vars: `DATABASE_URL`, `JWT_SECRET`, `SEED_ENABLED`, `SEED_KEY`, `LOG_LEVEL` (default `INFO`), `BCRYPT_ROUNDS` (fixed at 12), `EXPORT_HMAC_KEY`, `GRAPH_MAX_EVENTS`.
- `.env.example`.

**Design notes**
- *`LOG_LEVEL` defaults to INFO*, so debug-gated work (H4) is wasted work in every profile unless someone turns debug on.
- *`BCRYPT_ROUNDS` is fixed at 12* so no change to the app config can weaken the P10 restraint test.

**Done when:** the database starts, settings load, and a settings unit test passes.

---

### T03: Database models and migrations
**Size:** M | **Depends on:** T01, T02

**Build**
- Translate `Models.md` into SQLAlchemy 2.0 declarative models (all 37), with enum check constraints, JSONB, INET and the indexes listed there.
- Alembic initial migration (upgrade and downgrade).
- Session factory using the **sync engine** (psycopg 3).

**Design notes**
- *Handler style is mixed on purpose.* Most handlers are plain `def` (run in the thread pool). Only `GET /health` and `POST /auth/login` are `async def`, because P9 needs a handler that blocks the event loop and `/health` is the latency probe.
- *The database layer is clean.* No planted issues live in models.

**Done when:** `alembic upgrade head` and `downgrade base` both work on an empty database; a smoke test creates and rolls back one row of every model.

---

### T04: App skeleton and conventions
**Size:** M | **Depends on:** T03

**Build**
- App factory and one router per module.
- Error model and exception handlers (`ErrorResponse` from `Endpoints.md`).
- Pagination helper (`limit`/`offset` and the list envelope).
- Request-id middleware.
- Logging setup in `core/logging.py` (module loggers).
- JWT bearer dependency, role guard and tenant dependency (stubs, completed in T10).
- `GET /health` (`async def`, includes a DB check).

**Design notes**
- *This is the control layer.* Keep `core/` clean and efficient; it is used by every module.

**Done when:** contract tests pass for error shape, pagination envelope and `/health`.

---

### T05: Seed bootstrap endpoints
**Size:** S | **Depends on:** T03, T04

All seed endpoints live in `parcelpilot/dev/`, under `/api/v1/_seed`. They are enabled only when `SEED_ENABLED=1`, authenticate with an `X-Seed-Key` header (not JWT), and return `404` when disabled.

| Method | Path | Purpose | Built in |
|--------|------|---------|----------|
| POST | `/_seed/reset` | Truncate all tables and restart identities. Body `{ "confirm": true }`. | T05 |
| POST | `/_seed/tenants` | Create a tenant with one user per role and **known credentials**. Body `{ "slug", "name", "users": [...] }` (defaults provided). Returns the credentials. | T05 |
| GET | `/_seed/status` | Row counts per table, workload name, scale, `seeded_at`, tenants. | T05 |
| POST | `/_seed/workloads/{workload}` | Seed a workload. Body `{ "tenant_slug", "scale", "rng_seed", "domains" }`. Returns `202` `JobAccepted`. | T07 |
| GET | `/_seed/jobs/{job_id}` | Seed job progress per domain. | T07 |
| GET | `/_seed/samples` | Sample ids and keys for scenarios. Query `kind`, `n`. | T07 |
| GET | `/_seed/import-file` | Generate an import CSV or NDJSON. Query `workload`, `rows`, `bad_row_pct`, `format`. | T07 |

**Design notes**
- *Seed endpoints are the only way to create the first tenant and admin*, so this item must exist before the auth item can be tested.
- *Dev code is clean and excluded from analysis.* It is not in the ground truth and not in the analyzer view (T40).

**Done when:** reset, tenant creation and status work end to end; guard tests cover missing key, wrong key and disabled flag.

---

### T06: Workload definitions
**Size:** S | **Depends on:** T03

Define three workloads in `parcelpilot/dev/workloads.yaml`. `scale` (0.01-1.0) multiplies every volume. A fixed `rng_seed` makes data deterministic.

| Table / trait | `benign` (small shop) | `typical` (mid-size, used for human sessions) | `hostile` (adversarial) |
|---------------|----------------------|-----------------------------------------------|-------------------------|
| Warehouses | 4 | 4 | **1** |
| Customers | 2,000 | 30,000 | 200,000 |
| Categories | 100, depth 3 | 500, depth 5 | 5,000, **depth 40**, at most 800 siblings per node |
| Products | 5,000 | 20,000 | 50,000 |
| SKU scheme | random 3-letter prefix + number | random 3-letter prefix + number | **one shared prefix** (`ACM-000001`) |
| Stock levels | 20,000 | 80,000 | 50,000 (one per product, single warehouse) |
| Orders (history) | 20,000 over 90 days | 300,000 over 270 days | 1,000,000 over 270 days |
| Blocklist entries | 1,000 | 20,000 | **100,000** |
| Search terms | 50 | 500 | **5,000** |
| Tax rules | 20 | 200 | 2,000 |
| Discounts per bundle | 8 | 10 | **18** |
| Import rows (per file) | 10,000 | 200,000 | 2,000,000 |
| Shipment events (T28) | 50,000 | 500,000 | 5,000,000 |
| Bins per warehouse (T28) | 500 | 2,000 | 5,000 |
| Route stops (T28) | 50 | 300 | 1,500 |

**Design notes**
- *Two workloads are mandatory* (benign and hostile) so data-dependent issues (H5, H8, H2, P11) show up in one and stay quiet in the other. `typical` is the realistic middle used for general human-like sessions.
- *The hostile stock volume here replaces the table in the `Models.md` test-author notes* (those listed 500,000 stock rows for 50,000 products, which cannot be one row per product and warehouse).
- *Hostile data must cause slowness, not crashes.* Sibling lists are capped at 800 so H6's recursion stays under Python's default recursion limit.

**Done when:** `workloads.yaml` validates against a schema and a test asserts every volume is positive and monotone benign <= typical <= hostile where intended.

---

### T07: Seed generators and workload seeding endpoints
**Size:** L | **Depends on:** T05, T06

**Build**
- Generators in dependency order: tenants and users, warehouses, categories, products, stock, customers and addresses (with latitude/longitude), tax rules, discounts and bundles, blocklist, search terms, orders and items (with fraud checks).
- Bulk loading via **PostgreSQL `COPY`** in chunks, with progress reporting. Do not go through app services or the ORM row by row.
- Implement `POST /_seed/workloads/{workload}`, `GET /_seed/jobs/{job_id}`, `GET /_seed/samples`, `GET /_seed/import-file`.
- Hostile shapes: single warehouse, shared SKU prefix, deep category chain, large blocklist, many search terms.
- Seeding is deterministic and idempotent per tenant slug (`409` if already seeded, unless reset first).

**Design notes**
- *Seeding is excluded from profiles.* The harness seeds first and attaches the profiler afterwards, so seed code never appears in a flamegraph.
- *Samples endpoint lets scenarios behave like users* who pick real customers, SKUs and orders instead of guessing ids.

**Done when:** `benign` at scale 1.0 seeds in under 60 seconds; row counts match `workloads.yaml` within 1%; the same `rng_seed` gives an identical data hash; import file generator output imports cleanly at `bad_row_pct=0`.

---

### T08: Test infrastructure
**Size:** M | **Depends on:** T04, T07

**Build**
- pytest fixtures: ephemeral database per session, `seeded_benign` and `seeded_hostile` (small scale, built with the T07 generators), authenticated `httpx` clients per role.
- **Oracle framework:** record golden outputs from the unoptimized code for fixed inputs into `tests/oracles/<issue>.json`; comparators for exact, float tolerance, unordered and set equality. A `make oracles-record` target, with diffs reviewed in code review.
- **Benchmark helper:** wraps pytest-benchmark, writes `tests/bench/results/<issue>.json`; thresholds read from `ground_truth/issues.yaml`.
- **Tripwire marker** for tests that assert the malpractice is still present.
- Markers: `oracle`, `bench`, `tripwire`, `e2e`.

**Design notes**
- *Correctness oracle for every case.* AI optimizers sometimes change behaviour, so each issue's oracle must cover the edge cases listed in its item.
- *Clear ownership.* Each module owns its unit tests and oracle; separate `e2e` tests run the whole app, because fixes interact (see T46).

**Done when:** a toy function demonstrates oracle, tripwire and benchmark tests end to end.

---

### T09: Ground-truth manifest and hint hygiene
**Size:** S | **Depends on:** T01

**Build**
- `ground_truth/issues.yaml` with one entry per issue: `id`, `title`, `endpoints`, `planted_in` (file::function), `visible_in` (workloads), `profile_signature` (frames and expected share), `correct_fix_location`, `fix_scope` (`leaf` | `caller` | `architectural` | `none`), `difficulty_detect`, `difficulty_fix`, `oracle`, `benchmark_threshold`.
- Every later item adds its own entry.
- Hygiene rules and `tests/test_no_hints.py`: scan `parcelpilot/` for banned words (`slow`, `naive`, `bad`, `inefficient`, `TODO optimize`, issue IDs) and fail the build if found.

**Design notes**
- *Score blame, not just detection.* The manifest records which frame the correct fix touches, so a pipeline that edits the leaf with the highest `self_time` (P1, P5, H2) can be scored as wrong.
- *Restraint cases have `fix_scope: none`* (P10, P6).
- *Hints stay out of the app.* The ground truth, oracles and the "Test-author notes" in `Endpoints.md` and `Models.md` live outside the package and are stripped for the analyzer (T40).

**Done when:** schema validation test for the manifest and the hint scan both run in `make check`.

---

## Phase B: Core API

### T10: Auth
**Size:** M | **Depends on:** T04, T05, T08, T09

**Endpoints:** `POST /auth/login` (form), `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/users`.

**Malpractice: P9 + P10 (paired trap)**
- Planted in `auth/passwords.py` and `auth/api.py`. `login` is `async def` and calls `bcrypt.checkpw` **directly on the event loop**. `POST /auth/users` calls `bcrypt.hashpw` at cost 12.
- The bcrypt work is legitimately expensive (P10): the correct fix is to offload it (`anyio.to_thread` / `run_in_executor`), **not** to lower the cost or swap the algorithm.
- Refresh, logout, me use SHA-256 token hashing and are clean (controls).

**Extras for done**
- Oracle: login success and failure responses; stored hashes verify; assert every hash starts with `$2b$12$` so a "fix" cannot weaken the cost.
- Tripwire: while 10 concurrent logins run, `GET /health` latency exceeds a threshold (the loop is stalled).
- Benchmark: p95 `/health` latency during a login burst. Target: at least 5x lower after offloading. Per-login CPU time must stay the same.

**Design notes**
- *Pair the traps.* P9 and P10 sit in the same endpoint on purpose: the flamegraph shows only a big bcrypt box, and the real problem (blocking the loop) is invisible in a CPU profile. The harness needs a latency probe for it (T25).

---

### T11: Customers
**Size:** S | **Depends on:** T10

**Endpoints:** `POST /customers`, `GET /customers/{customer_id}`.

**Malpractice:** none (control). Use eager loading for addresses and a single indexed query.

**Design notes**
- *Clean control modules.* These endpoints give the pipeline code that should produce "no change". Record a benchmark baseline so any analyzer edit that makes them slower is caught.

---

### T12: Warehouses
**Size:** S | **Depends on:** T10

**Endpoints:** `POST /warehouses`, `GET /warehouses`.

**Malpractice:** none (control). Uppercase `code` validation.

---

### T13: Catalog categories
**Size:** M | **Depends on:** T10

**Endpoints:** `POST /catalog/categories`, `GET /catalog/categories`, `GET /catalog/categories/{id}/path`, `GET /catalog/categories/{id}/rollup`.

**Malpractice: H6 (recursion with slicing)**
- Planted in `catalog/tree.py`, called from `catalog/api.py`.
- `find_chain(cats, target_id)` loads all tenant categories into a list ordered by depth and recurses on `cats[1:]` to collect the ancestor chain.
- `rollup(node, cats)` recurses over `children[1:]` for each sibling list, so every step copies the rest of the list.
- Leave the recursion limit at its default.
- `POST /catalog/categories` and the plain tree listing are clean (dict by `parent_id`).

**Extras for done**
- Oracle: path for every node of the benign tree; rollup counts with and without `include_inactive`.
- Tripwire: growth ratio (time for 2n nodes divided by time for n nodes) is above 3 on a synthetic chain.
- Benchmark: hostile tree (depth 40, 5,000 nodes). Target: at least 10x faster after fixing.

**Design notes**
- Quiet on benign (depth 3), visible on hostile. Record both in `visible_in`.

---

### T14: Products and stock
**Size:** L | **Depends on:** T12, T13

**Endpoints:** `POST /catalog/products`, `POST /catalog/products/bulk`, `GET /catalog/products`, `GET /catalog/products/{sku}`, `GET /catalog/stock`, `PUT /catalog/stock`, `POST /catalog/stock/lookup`.

**Malpractice: H5 + P11 (data-dependent)**
- Planted in `catalog/keys.py::SkuKey`, used by `catalog/stock_service.py`.
- `SkuKey.__hash__` returns `hash((warehouse_code, sku[:3]))` while `__eq__` compares the full `(warehouse_code, sku)`. With benign data (random 3-letter SKU prefixes, 4 warehouses) hashes spread well. With hostile data (one warehouse, shared prefix `ACM`) every key collides and dict operations become O(n) each.
- Used in `POST /catalog/stock/lookup` (builds `{SkuKey: row}`) and `PUT /catalog/stock` (matches updates to existing rows).

**Controls (written well)**
- `POST /catalog/products` and `/bulk` use bulk insert, `GET /catalog/products` uses SQL filters and pagination, and **`GET /catalog/products/{sku}` is the explicit "already-optimal" control**.

**Extras for done**
- Oracle: lookup results (including missing keys) and resulting stock rows after `set` and `delta` updates are identical.
- Tripwire: distinct-hash ratio is below 1% on the hostile key set and above 50% on the benign set.
- Benchmark: hostile lookup of 10,000 keys. Target: at least 20x faster after fixing.

**Design notes**
- *Pair the traps.* The benign profile must **not** show this issue. A pipeline given only the benign profile should be unable to find it (tests P11: the AI should ask for or use a representative profile). Checked in T26.

---

### T15: Discounts, quotes and pricing/tax services
**Size:** M | **Depends on:** T14

**Endpoints:** `POST /pricing/discounts`, `GET /pricing/discounts`, `POST /pricing/quotes`, `POST /pricing/quotes/batch`, `GET /pricing/quotes/{quote_id}`.

**Internal services (clean, shared with orders):** `pricing/service.py::price_line`, discount application with stacking groups, `tax/service.py::tax_for_line` (rule lookup by country, region, category and priority; half-up integer rounding).

**Malpractice: H7 (cache that never hits)**
- Planted in `pricing/cache.py`, applied in `pricing/service.py`.
- `@lru_cache(maxsize=None)` on `compute_quote(sku, quantity, customer_id, currency, requested_at)`. `requested_at` (microsecond precision) is part of the key, so no hits and the cache grows without bound.

**Extras for done**
- Oracle edge case: quotes at timestamps either side of a discount's `valid_to`. A naive fix that drops the timestamp entirely would give wrong prices, so the correct fix must key on discount validity windows.
- Tripwire: `cache_info().hits == 0` after N requests that differ only by timestamp, and `currsize` equals N.
- Benchmark: 10,000 quotes differing only by `requested_at`. Target: at least 3x faster, with bounded memory (checked with `tracemalloc`).

**Design notes**
- The growing cache raises memory and later GC cost. This interacts with P5 (see T46).

---

### T16: Bundles and best discount
**Size:** M | **Depends on:** T14, T15

**Endpoints:** `POST /pricing/bundles`, `POST /pricing/bundles/best-discount`.

**Malpractice: P4 (recursion without memoization)**
- Planted in `pricing/bundles.py::best_combination`.
- Recursive include/exclude search over candidate discounts: `best(i, chosen, subtotal)` returns the max of skipping or taking discount `i`, with stacking-group and minimum-subtotal checks, and **no memoization or pruning**. It evaluates all `2^n` subsets and reports that count as `combinations_evaluated`.
- `POST /pricing/bundles` is clean.

**Extras for done**
- Oracle: identical `best_combination`, savings and totals. Ties break deterministically on the lowest discount-id list.
- Tripwire: `combinations_evaluated == 2**n` for every input.
- Benchmark: 8 candidates (benign) vs 18 candidates (hostile, about 262,000 evaluations). Target: at least 50x faster on hostile.

**Design notes**
- Recursive frames make the flamegraph deep and narrow, and `total_time` double-counts nested frames. Checks that the pipeline reads this correctly.

---

### T17: Fraud screening and blocklist
**Size:** M | **Depends on:** T07, T10

**Endpoints:** `GET /fraud/blocklist`, `POST /fraud/blocklist`, `DELETE /fraud/blocklist/{entry_id}`, `POST /fraud/screen`, `POST /fraud/screen/batch`.

**Malpractice: H2 + P1 (hidden list membership, self time in a builtin)**
- Planted across three files:
  - `config/lists.py::load_blocklists` builds `BLOCKLISTS = {entry_type: [values...]}` as **lists**.
  - `fraud/lookup.py::is_blocked(entry_type, value)` does `value in BLOCKLISTS[entry_type]`.
  - `fraud/screening.py::screen_order` calls `is_blocked` for email, ip, name, phone and address; the batch endpoint loops over orders. `orders/service.py` also calls `screen_order`.
- In the flamegraph the self time lands in `list.__contains__` (a C frame). The correct fix is **two frames up**, at the list's creation.
- Blocklist `POST` and `DELETE` are clean; the lists are loaded at startup and reloaded once per mutating request.

**Extras for done**
- Oracle over 2,000 orders: decision, score and matches are identical. Include expired entries (must be ignored), case-insensitive email matching, and phone and address normalization.
- Tripwire: `type(BLOCKLISTS["email"]) is list`.
- Benchmark: hostile (100,000 entries), batch of 2,000 orders. Target: at least 50x faster.
- `ground_truth` records `fix_scope: caller` and `correct_fix_location: config/lists.py::load_blocklists`. Fixing only the leaf or `is_blocked` counts as a partial hit.

**Design notes**
- *Spread the cross-file cases.* The cost is defined in one module and triggered from two others.
- *H4 call site:* one debug log in `screen_order` that formats the match list.

---

### T18: Orders
**Size:** L | **Depends on:** T11, T15, T17

**Endpoints:** `POST /orders`, `GET /orders`, `GET /orders/{order_id}`, `PATCH /orders/{order_id}/status`.

**Malpractice: H3 + H4 + P3 (and H2 via fraud screening)**
- **H3, repeated serialization:** `orders/api.py::create_order` does `json.dumps(model.model_dump())`, passes the string to `OrdersService.create`, which does `json.loads`, builds a dict, `json.dumps` again for `OrdersRepo.insert`, which does `json.loads` once more before storing `raw_payload`.
- **P3, flat profile:** each layer re-validates the payload with `OrderCreate.model_validate(...)`, makes `dict(...)` and `copy.deepcopy` copies of the payload, and calls a `log_event()` helper that does a small `json.dumps` of context. None of these is large; together they cost roughly 30%.
- **H4, eager log formatting:** 4-6 call sites like `logger.debug(f"order state: {render_order(order)}")` across `api`, `service` and `repo`. One renders all items (at least 5% of the request); the rest are cheap, so impact varies.
- Calls fraud screening from T17 (H2 comes along).

**Controls (written well):** `GET /orders` (SQL filtering and pagination), `GET /orders/{id}`, `PATCH /orders/{id}/status` (transition table), stock reservation as a single `UPDATE ... RETURNING`.

**Extras for done**
- Oracle: 200 fixed order requests give identical responses; stored `raw_payload` is semantically equal.
- Tripwire: `json.loads` and `json.dumps` are each called at least 3 times per `POST /orders`; `model_validate` at least 3 times; `render_order` runs although DEBUG is off.
- Benchmark: 500 orders. Target: at least 1.3x faster after all three fixes.
- Flat-profile check (put in T26): no single frame holds more than 12% of the endpoint's self time.

**Design notes**
- *Spread the cross-file cases.* H3 and P3 span `orders/api.py`, `orders/service.py`, `orders/repo.py` and `core/logging.py`.

---

### T19: Bulk imports and normalization
**Size:** L | **Depends on:** T11, T14, T18

**Endpoints:** `POST /imports/orders` (multipart), `GET /imports/{job_id}`, `GET /imports/{job_id}/rows`, `POST /imports/{job_id}/normalize`.

**Build (clean):** streaming CSV/NDJSON parse, staging rows via `COPY`, grouping rows by `external_ref`, order creation with bulk inserts, background processing (the request returns `202`).

**Malpractice: P2 + P6 (many cheap calls, profiler-inflated helpers)**
- Planted in `imports/normalize.py::normalize_job` and `imports/cleaners.py`.
- The job loops over every staged row (up to 2 million) and calls tiny helpers per row: `to_cents("1,299.50")`, `clean_postal(" 04229 ")`, `title_city("leipzig")`, `geocode_stub(postal, country)` (deterministic, no network). Each costs 1-3 microseconds.
- No frame has large `self_time`; the cost is the row loop's `total_time` and the call count.
- Under a sampling profiler (py-spy) the helpers look minor. Under a deterministic profiler (cProfile) they look inflated.

**Extras for done**
- Oracle on a 10,000-row fixture: identical normalized addresses and prices. Edge cases: thousands separators, whitespace, lowercase cities, missing region, trailing zeros.
- Tripwire: `to_cents` is called once per row.
- Benchmark: 200,000 rows. Target: at least 3x faster by batching or vectorizing.
- Manifest: `fix_scope: caller`; the helpers themselves are not the fix location (P6 restraint).

**Design notes**
- *Decide whether call counts are exposed* (T23). Without them P2 may be undetectable by design; with cProfile they are available, so the harness produces both profile types for this endpoint.

---

### T20: Sales reports
**Size:** M | **Depends on:** T18

**Endpoints:** `POST /reports/sales`, `GET /reports/sales/{run_id}/rows`.

**Build (clean):** SQL group-by to compute rows, bulk write of `ReportRow`.

**Malpractice: H1 (property recomputes on every access)**
- Planted across files:
  - `reports/models.py::Report.sorted_rows` is a `@property` that sorts `self._rows` with `reports/keys.py::expensive_key` (Unicode normalize plus `casefold` for labels).
  - `reports/service.py::render_page` loops `for i in range(len(report.sorted_rows))` and indexes `report.sorted_rows[i]`, so each iteration sorts twice.
  - `reports/api.py` passes `sort_by`/`order` through `report.configure(...)`.

**Extras for done**
- Oracle: page contents for every `sort_by` value, including ties (stable sort order must be preserved).
- Tripwire: `sorted` is called at least `page_size` times per request.
- Benchmark: 50,000 rows, `limit=500`. Target: at least 10x faster.

**Design notes**
- *Spread the cross-file cases.* The property is defined in one module and abused in another.

---

### T21: Daily analytics
**Size:** M | **Depends on:** T18

**Endpoints:** `POST /analytics/daily/compute`, `GET /analytics/daily`.

**Build (clean):** per-day SQL aggregation; bulk upsert of `DailySalesSummary`; `GET /analytics/daily` is a control.

**Malpractice: H10 (growing DataFrame)**
- Planted in `analytics/daily.py::compute_range`.
- Aggregation granularity is `(date, category_id)`, producing about 55,000 rows for `typical`. Each row is appended with `df = pd.concat([df, pd.DataFrame([row])])`, copying everything accumulated so far.

**Extras for done**
- Oracle: identical summaries and dtypes (integers stay integers).
- Benchmark: `typical` range of 270 days. Target: at least 5x faster (collect into a list and build once).

---

### T22: Tax estimate
**Size:** S | **Depends on:** T13, T15

**Endpoint:** `POST /analytics/tax/estimate`.

**Malpractice: H9 (`np.vectorize` pretending to be vectorized)**
- Planted in `analytics/tax.py`.
- `tax_vec = np.vectorize(lambda amt, cat: compute_tax(amt, rules_for(cat)))` applied to the line arrays. It reads like NumPy but runs a Python loop.
- `compute_tax` uses integer half-up rounding: `(amount * rate_bps + 5000) // 10000`.

**Extras for done**
- Oracle edge cases: amounts that land exactly on `.5` boundaries. NumPy's default rounding is banker's rounding, so a careless vectorized rewrite changes results; the oracle must catch that. Include threshold rules and priority ties.
- Benchmark: 100,000 lines. Target: at least 20x faster.

**Design notes**
- A naive analyzer may approve this because the code looks like NumPy.

---

## Phase C: Profiling harness

### T23: Decision: profile artifact format
**Size:** S | **Depends on:** none (needs your input; blocks T24)

Decide what the harness must emit so it matches what your pipeline already consumes.

- Flamegraph format: SVG, collapsed stacks, or speedscope JSON?
- `self_time` / `total_time`: CSV columns, `pstats`, or derived from stacks?
- Are **call counts** exposed to the analyzer? (Only cProfile provides them; without them P2 may be undetectable.)
- How should recursion be shown in `total_time` (naive sum of nested frames, or unique per sample)? P4 tests this.

**Default if undecided:** py-spy collapsed stacks plus speedscope JSON and a rendered SVG; `functions.csv` with `self_time_s`, `total_time_s`, `self_pct`, `total_pct`, and `calls` (filled only from the cProfile run).

**Design notes**
- *Decide whether call counts are exposed.* This decision directly affects whether P2 and P6 are fair tests.

**Decision (T23):** Emit py-spy `stacks.collapsed`, `speedscope.json`, and rendered `flamegraph.svg`; emit cProfile `profile.pstats` plus a `functions.csv` with `self_time_s`, `total_time_s`, `self_pct`, `total_pct`, and `calls`. The shared CSV uses blank `calls` for py-spy captures and exact call counts from cProfile. Use each profiler's native cumulative-time accounting; for sampled stacks, count a recursive function at most once per sample when deriving inclusive time so nested recursion does not inflate totals.

---

### T24: Profile harness core
**Size:** L | **Depends on:** T07, T23

**Build** `profiling/run.py` and `profiling/capture.py`, run as:

```
python -m profiling.run --workload benign|typical|hostile --scale 0.1 --duration 300 --profiler pyspy|cprofile
```

**Run sequence**
1. Start Postgres, run migrations, call `POST /_seed/reset`.
2. Start the API with uvicorn (**single worker**, so py-spy attaches to one PID).
3. Call `POST /_seed/tenants` and `POST /_seed/workloads/{workload}`; wait for the seed job.
4. Warm-up scenario (60 s, not recorded).
5. Attach the profiler and run the human-like scenarios (T25) for the duration.
6. Stop and post-process into artifacts.

**Artifacts** (`profiles/<workload>/<UTC-timestamp>/`)

```
meta.json            git sha, workload, scale, duration, versions, profiler flags, per-endpoint hit counts, error rate
pyspy/               flamegraph.svg, stacks.collapsed, speedscope.json
cprofile/            profile.pstats, functions.csv   (call counts available here)
functions.csv        self_time / total_time table
locust/              stats.csv, failures.csv
validation.json      written by T26
```

- cProfile mode: start the server through `profiling/serve_cprofile.py`, which enables cProfile around the app and dumps `.pstats` on `SIGTERM`.
- Check readiness through `/health`; fail fast if the profiler lacks permission (ptrace).

**Design notes**
- *Profile the human phase only.* Seeding is excluded, and a separate startup profile covers P14 (T41).
- *Provide multiple captures per case.* The same code is profiled under benign and hostile workloads, which is what P11 needs.
- *py-spy permissions:* in containers add `SYS_PTRACE`; on macOS use `sudo`; on Linux check `kernel.yama.ptrace_scope`.

**Done when:** one benign run produces all artifacts and `meta.json` is complete.

---

### T25: Human-like scenarios (Must endpoints)
**Size:** L | **Depends on:** T24, T10-T22

Locust (headless) with `SequentialTaskSet` flows, think time between actions (about 1-8 seconds, log-normal), and a ramp from 1 to 20 users over 60 seconds.

| Persona | Weight | Typical flow | Planted issues exercised |
|---------|--------|--------------|--------------------------|
| Shopper (phone or chat agent) | 35% | login, browse products, search, check stock, request quote, create customer (sometimes), place order, view order | P9/P10, H7, H3/H4/P3, H2/P1 |
| Ops clerk | 20% | login, list orders with filters, open order, change status, screen suspicious order | P9/P10, H2/P1 |
| Catalog manager | 15% | login, category tree, path, rollup, bulk product create, stock lookup and update | H6, H5/P11 |
| Pricing admin | 10% | login, create discounts, create bundle, best discount | P4 |
| Analyst | 10% | login, run sales report, page through rows with different sorts, compute and read daily analytics, tax estimate | H1, H10, H9 |
| Integrator (batch) | 5% | get an import file from `/_seed/import-file`, upload, poll status, normalize, poll, batch fraud screen | P2/P6, H2/P1 |
| Latency probe | 1 user | `GET /health` every second | detects P9 event-loop stalls |

- Scenarios fetch real ids and keys from `GET /_seed/samples`.
- Tolerate expected errors (`409` duplicates, `422` validation) and reuse tokens with refresh.
- Run the same scenarios against all workloads; only the data differs.
- Per-endpoint hit counts are written to `meta.json`.

**Design notes**
- *Pair the traps in traffic as well:* login is in every persona, so P9's loop stalls hit all flows, and the latency probe makes it measurable.

**Done when:** a 5-minute `typical` run exercises every planted-issue endpoint at least 30 times with an error rate below 1%.

---

### T26: Expected-signal validation
**Size:** M | **Depends on:** T09, T25

Create `ground_truth/expected_signals.yaml` and `profiling/validate.py`. After each run, check and write `validation.json` (non-zero exit on failure):

1. Every planted-issue endpoint was hit at least N times, with error rate below 1%.
2. **Visibility:** the planted frame holds at least X% of `total_time` in the workloads where it should be visible.
3. **Absence:** the same frame stays below a lower threshold where it should be quiet (for example H5 and H6 on `benign`).
4. **Flat profile:** `POST /orders` has no single frame above 12% self time (P3).
5. **P9 latency probe:** `/health` p95 latency during login bursts exceeds a threshold.
6. **P1 shape:** self time on `list.__contains__` is high while the creating frame is not hot.

**Design notes**
- *Score blame, not just detection.* The signals file ties each expected hot frame to the `correct_fix_location` from the manifest.

**Done when:** validation passes on `benign` and `hostile` runs for all Must issues, and fails when an issue is deliberately removed.

---

### T27: Dev entrypoints, docs and app CI
**Size:** S | **Depends on:** T08, T26

- Makefile: `up`, `down`, `migrate`, `seed WORKLOAD=...`, `test`, `oracles-record`, `bench`, `profile WORKLOAD=...`.
- `docs/PROFILING.md` (permissions, flags, reading the artifacts) and `docs/WORKLOADS.md`.
- App CI: lint, unit, api, oracle and tripwire tests, plus a smoke profile at `--scale 0.02 --duration 60`.

**Done when:** from a fresh clone, `make up seed WORKLOAD=benign profile WORKLOAD=benign` produces artifacts.

---

# SHOULD

### T28: Seed extensions
**Size:** M | **Depends on:** T07

- Add `shipments` and `shipment_events` (hostile target: 5,000,000 events), `bins` and `slot_assignments`, route stops (geocoded delivery addresses), and demand history derived from orders.
- Extend `domains` on `POST /_seed/workloads/{workload}` and the `GET /_seed/samples` kinds (`shipment_ids`, `tracking_numbers`, `warehouse_ids`).

**Design notes**
- *Memory sizing:* the in-memory graph for P5 holds one dict per event, so a 5M-event load needs several GB. Default `GRAPH_MAX_EVENTS` to 1,000,000 for CI and allow 5,000,000 for full runs.

---

### T29: Shipments and event graph
**Size:** L | **Depends on:** T18, T28

**Endpoints:** `POST /shipments`, `POST /shipments/events/bulk`, `GET /shipments/{id}/timeline`, `POST /shipments/graph/rebuild`, `GET /shipments/graph/stats`.

**Build (clean):** shipment creation, bulk event ingest with `executemany`, timeline query, stats grouping with a dict counter.

**Malpractice: P5 (GC pressure misattributed)**
- Planted in `shipments/graph.py::build_graph`.
- Loads every event into the graph as a plain dict with nested containers (`{"id", "shipment_id", "type", "children": [], "meta": {...}}`), so millions of small container objects trigger repeated full GC passes.
- A separate cheap-looking helper `enrich_event` allocates during the build, so sampled GC time lands on it and it *looks* guilty.
- The correct fix is the data representation (`__slots__`, tuples or arrays) and GC tuning (`gc.freeze()`), not `enrich_event`.

**Extras for done**
- Oracle: `stats` output identical for all `group_by` values.
- Tripwire: GC collection count during `build_graph` is above N.
- Benchmark: build time with `gc.disable()` is at least 25% shorter than with GC on (proves GC is the cost). Target for a real fix: at least 2x faster build.
- Manifest: `fix_scope: architectural`; `enrich_event` is listed as the **innocent** frame.

**Design notes**
- Strong false-positive trap: the "hot" frame is innocent.
- H4 call site: a debug log per batch of events with a formatted sample.

---

### T30: Routing
**Size:** M | **Depends on:** T29

**Endpoints:** `POST /routing/routes`, `POST /routing/routes/{id}/optimize`, `GET /routing/routes/{id}`.

**Malpractice: P12 (needs a build-level change)**
- Planted in `routing/optimizer.py::two_opt`.
- Pure-Python 2-opt with nested loops, computing haversine distances with `math` for each pair on lists of dicts. It holds about 80% of runtime on `typical`.
- `POST /routing/routes` and `GET` are clean.

**Extras for done**
- Oracle: result is a valid permutation, distance is no worse than the baseline's, and the algorithm is deterministic (first-improvement, fixed order). Keep `time_limit_ms` unset in tests, because time limits make results nondeterministic.
- Benchmark: 1,500 stops. Target: at least 20x faster with a NumPy distance matrix; Numba or Cython may go further.
- Manifest: records that a proportionate fix is NumPy first, with Numba/Cython an optional step that needs a build or dependency change.

**Design notes**
- Tests whether the AI proposes a proportionate fix and states the tradeoff.

---

### T31: Warehouse bins and slotting
**Size:** M | **Depends on:** T12, T18, T28

**Endpoints:** `POST /warehouses/{id}/bins/bulk`, `POST /warehouses/{id}/slotting/runs`, `GET /warehouses/{id}/slotting/runs/{run_id}`.

**Malpractice: P13 (memory layout and dtype)**
- Planted in `slotting/analysis.py`.
- Builds a 5,000 x 5,000 `float64` distance matrix (about 200 MB where `float32` would do), then loops `for j in range(a.shape[1]): col_sum = a[:, j].copy().sum()`, giving strided access plus an unnecessary copy.
- Runs as a background job in a worker thread (not on the event loop).

**Extras for done**
- Oracle: results equal within relative tolerance `1e-4` (allows `float32`).
- Benchmark: 5,000 bins. Target: at least 10x faster.

**Design notes**
- The profile shows a slow `sum` with no hint as to why; this is deliberately invisible at function level.

---

### T32: Search terms and tagging
**Size:** M | **Depends on:** T07, T14

**Endpoints:** `POST /catalog/search/terms`, `POST /catalog/search/tag`.

**Malpractice: H8 (regex cache thrash)**
- Planted in `catalog/tagging.py`.
- For each product and each term: `re.search(rf"\b{re.escape(term)}\b", text, flags)` with a dynamically built pattern. Benign (50 terms) fits the `re` cache; hostile (5,000 terms) exceeds its roughly 512 entries and recompiles constantly.
- Terms endpoint is clean (bulk insert).

**Extras for done**
- Oracle: identical tag sets for `whole_word` and `substring`, case-sensitive and not, with special characters in terms.
- Benchmark: hostile request on a product subset sized to take 5-30 seconds (about 500 products x 5,000 terms). Target: at least 20x faster with a precompiled or combined pattern.

**Design notes**
- Quiet on benign, visible on hostile. Record in `visible_in`.

---

### T33: Extra capture modes
**Size:** M | **Depends on:** T24

- Add `--capture subprocesses` (py-spy `--subprocesses`), `--capture gil` (`--gil`) and `--capture idle` (`--idle`) to the harness, each in its own artifact folder.
- Deterministic cProfile run for P6 is already in T24; this item covers the multi-process and idle-aware modes.

**Design notes**
- Worker profiles are separate from the parent's, and lock waits look like non-CPU time; the harness must capture both views so P7 and P8 are testable. Because the target is CPU time, record wall-time and CPU-time views separately.

---

### T34: Demand scoring
**Size:** L | **Depends on:** T18, T28, T33

**Endpoints:** `POST /scoring/jobs`, `GET /scoring/jobs/{id}`, `GET /scoring/results`.

**Malpractice: P7 (pickling dominates)**
- Planted in `scoring/batch.py`.
- Runs on a `ProcessPoolExecutor`; every task receives a **large pandas DataFrame** (the sales history slice) as an argument, while the actual per-chunk computation is small. Pickling and IPC dominate and it can be slower than serial.
- Result writes use bulk insert (clean).

**Extras for done**
- Oracle: identical `DemandScore` rows (to fixed precision) for fixed inputs.
- Benchmark: `typical` history. Target: at least 3x faster by sending ids and loading data in workers, using shared memory, or a pool initializer.
- Expected signal (T26): in the `subprocesses` capture, `pickle` and `multiprocessing` frames hold at least 30% of parent time.

**Design notes**
- The cost appears indirectly (parent idle time and serialization frames), so the AI must infer it.

---

### T35: Metrics
**Size:** M | **Depends on:** T10, T33

**Endpoints:** `POST /metrics/events`, `GET /metrics/summary`.

**Malpractice: P8 (lock contention and GIL waiting)**
- Planted in `metrics/collector.py`.
- A `ThreadPoolExecutor(8)` processes events; each worker wraps the **whole** `update_counter` in one global `threading.Lock()`, including the CPU work (sorting labels, canonical JSON, MD5 of labels).
- `GET /metrics/summary` is clean.

**Extras for done**
- Oracle: counter values equal after a fixed event stream.
- Benchmark: 10,000 events. Target: at least 3x faster by narrowing the critical section or aggregating per thread.
- Expected signal: with `--idle`/`--gil` captures, `lock.acquire` frames are visible; without them the problem looks invisible.

**Design notes**
- Tests whether the AI separates wall time from CPU time.

---

### T36: Exports
**Size:** M | **Depends on:** T18, T29

**Endpoints:** `POST /exports`, `GET /exports/{id}`, `GET /exports/{id}/download`.

**Malpractice: P10 (restraint test)**
- Planted in `exports/archive.py`, but the code is **correct and well written**: it streams rows in chunks, compresses with gzip and signs with HMAC-SHA256. These dominate `self_time` because they are legitimately expensive.
- The right response is "inherent cost, no change", or at most a note about cheaper settings that change the output.

**Extras for done**
- Oracle: output SHA-256 and signature are identical for fixed input; any change to compression level or signing breaks it.
- Manifest: `fix_scope: none`.

---

### T37: Scenarios for Should endpoints
**Size:** M | **Depends on:** T25, T29-T36

Add personas to the harness:

| Persona | Flow | Issues exercised |
|---------|------|------------------|
| Warehouse manager | create bins, run slotting, poll result | P13 |
| Dispatcher | create shipments, ingest events, create route, optimize, fetch route | P5 (events), P12 |
| Data scientist | start scoring job, poll, query results | P7 |
| Catalog manager (extended) | add search terms, run tagging | H8 |
| Monitoring agent | post metric events every few seconds, read summary | P8 |
| Admin | start export, poll, download | P10 |
| Admin (graph) | rebuild graph, read stats | P5 |

Update `expected_signals.yaml` with the Should issues.

---

### T38: Reference fixes and speedup tests
**Size:** L | **Depends on:** T36

- `reference_fixes/<issue>.py` holds a hand-written optimized implementation for each of the 24 issues (or an explicit "no change" note for P10 and P6).
- Tests assert that each reference fix passes its oracle and reaches the manifest's speedup threshold.

**Design notes**
- Proves the benchmark targets are achievable and the oracles are fair. Reference fixes never live in `parcelpilot/`.

---

### T39: Containerized app and profiling
**Size:** S | **Depends on:** T24

- Dockerfile for the API with py-spy installed, and a compose profile that adds `cap_add: [SYS_PTRACE]` so the full harness runs in containers.

---

### T40: Analyzer-view packaging and leak check
**Size:** S | **Depends on:** T09, T36

- `scripts/make_analyzer_view.py` produces a sanitized copy: removes `ground_truth/`, `reference_fixes/`, `tests/oracles/`, the "Test-author notes" sections of `Endpoints.md` and `Models.md`, and `parcelpilot/dev/`.
- Leak check: scans the output for issue IDs, banned hint words and manifest file names; fails the build if any appear.

---

# COULD

### T41: CLI worker and startup profile
**Size:** M | **Depends on:** T19, T29, T34, T36

**Malpractice: P14 (import-time and startup cost)**
- Planted in `cli/worker.py`.
- `parcelpilot-worker` (commands `import-orders`, `score`, `export`, `rebuild-graph`) imports pandas, scipy and scikit-learn at module top level, although most commands use only some of them.
- Add a startup profile mode to the harness (`py-spy record` from process start, plus `python -X importtime`).

**Extras for done:** oracle on command output; benchmark on `parcelpilot-worker --help` and a short run. Target: at least 3x faster with lazy imports.

---

### T42: Pre-recorded profile fixtures and synthetic hard cases
**Size:** M | **Depends on:** T26, T37

- Commit sample outputs from real harness runs (benign and hostile) so the pipeline can be unit-tested without running the whole system.
- Add hand-built synthetic `pstats` and flamegraph files for cases that are awkward to reproduce live: flat profile (P3), GC misattribution (P5), recursion double-counting (P4), idle-only lock waits (P8).

---

### T43: Profile diff tool and benchmark history
**Size:** M | **Depends on:** T26

- `profiling/diff.py` compares two profile runs (benign vs hostile for P11, before vs after an AI fix) and lists frames whose share changed most.
- Store benchmark results over time to spot regressions.

---

### T44: Marginal-gain traps and extra controls
**Size:** S | **Depends on:** T18, T19

- Add a few spots where the "obvious" optimization gains little or is wrong:
  - String building with `+=` in a loop (CPython often optimizes it).
  - `try/except KeyError` in a hot path where misses are rare (replacing it can be slower).
- Add extra already-optimal helpers with benchmark baselines.

**Design notes**
- Checks that the pipeline does not claim improvements that are not real.

---

### T45: Bonus patterns from the first list (feature-flagged)
**Size:** M | **Depends on:** T19

- Behind `BONUS_PATTERNS=1` (off by default so the main controls stay clean): per-row commit during import staging, N+1 queries when listing orders with items, list membership in loops, re-reading a config file inside a loop.
- Tracked in the manifest as `B1`, `B2`, ... separate from the 24 core issues.

---

### T46: Fix-interaction tests
**Size:** S | **Depends on:** T08, T15, T29

- E2E tests applying one reference fix at a time and checking side effects: for example, fixing H7 (bounded cache) lowers memory and changes GC behaviour seen in P5; fixing H2 shifts the flamegraph shape for `POST /orders`.

---

### T47: Nightly full-scale run
**Size:** S | **Depends on:** T27, T37

- Scheduled CI job: `hostile` at `--scale 1.0`, validation, artifacts uploaded, benchmark history updated (needs T43 for history; otherwise artifacts only).

---

# WON'T (this iteration)

- A frontend or admin UI.
- Real external integrations: payment gateway, carrier APIs, geocoding provider, email or SMS.
- Production hardening: rate limiting, SSO or OAuth, secrets manager, Kubernetes or Helm, horizontal scaling, observability stack.
- Fixing the planted issues inside the app. The app stays unoptimized; fixes exist only in `reference_fixes/`.
- Building or changing the AI analyzer or the CI pipeline itself (it already exists on your side).
- Async database drivers or other database engines.
- Cython or Numba builds inside the main app (the P12 fix is evaluated only in `reference_fixes/`).
- Cursor pagination, full-text search and other features that carry no test value.

---

# Issue placement matrix

| Issue | Endpoint(s) | Item | Planted in | Visible in | Correct fix location |
|-------|-------------|------|------------|-----------|----------------------|
| H1 | `POST /reports/sales`, `GET /reports/sales/{run_id}/rows` | T20 | `reports/models.py::Report.sorted_rows`, abused in `reports/service.py` | all | `Report.sorted_rows` (compute once or `cached_property`) |
| H2 | `POST /fraud/screen`, `/fraud/screen/batch`, `POST /orders` | T17 | `config/lists.py`, `fraud/lookup.py`, `fraud/screening.py` | hostile strongly, benign weakly | `config/lists.py::load_blocklists` |
| H3 | `POST /orders` | T18 | `orders/api.py` to `service.py` to `repo.py` | all | remove round-trips in the three layers |
| H4 | `POST /orders` (plus screening, imports, events) | T18 (T17, T19, T29) | `core/logging.py` helper and call sites | all | lazy `%s` logging at each call site |
| H5 | `POST /catalog/stock/lookup`, `PUT /catalog/stock` | T14 | `catalog/keys.py::SkuKey` | hostile only | `SkuKey.__hash__` |
| H6 | category tree, path, rollup | T13 | `catalog/tree.py` | hostile mainly | iterate with indices or parent dict |
| H7 | `POST /pricing/quotes`, `/batch` | T15 | `pricing/cache.py` and `pricing/service.py` | all | cache key (validity window, not timestamp) |
| H8 | `POST /catalog/search/tag` | T32 | `catalog/tagging.py` | hostile only | precompile or combined pattern |
| H9 | `POST /analytics/tax/estimate` | T22 | `analytics/tax.py` | all | group and use `np.where` or ufuncs |
| H10 | `POST /analytics/daily/compute` | T21 | `analytics/daily.py` | all | collect list, build DataFrame once |
| P1 | `POST /fraud/screen` | T17 | same as H2 | hostile | same as H2 (caller, not leaf) |
| P2 | `POST /imports/{id}/normalize` | T19 | `imports/normalize.py` | all | batch the row loop |
| P3 | `POST /orders` | T18 | orders layers and `core/` helpers | all | many small changes (no single fix) |
| P4 | `POST /pricing/bundles/best-discount` | T16 | `pricing/bundles.py` | hostile strongly | memoize, DP or prune |
| P5 | `POST /shipments/graph/rebuild` | T29 | `shipments/graph.py::build_graph` | all, bigger on hostile | data representation and GC tuning (`enrich_event` is innocent) |
| P6 | `POST /imports/{id}/normalize` | T19 | `imports/cleaners.py` | cProfile capture only | do not edit the helpers (fix the caller, as P2) |
| P7 | `POST /scoring/jobs` | T34 | `scoring/batch.py` | `subprocesses` capture | send ids or use shared memory |
| P8 | `POST /metrics/events` | T35 | `metrics/collector.py` | `--idle` / `--gil` capture | narrow the lock scope |
| P9 | `POST /auth/login` | T10 | `auth/api.py::login` | latency probe | offload to a thread or executor |
| P10 | `POST /auth/login`, `POST /exports` | T10, T36 | `auth/passwords.py`, `exports/archive.py` | all | none (inherent cost) |
| P11 | stock lookup, search tag, fraud screening | T14, T32, T17 | data shape (see `workloads.yaml`) | hostile only | representative profile, then fix H5, H8, H2 |
| P12 | `POST /routing/routes/{id}/optimize` | T30 | `routing/optimizer.py::two_opt` | all | NumPy first; Numba or Cython optional |
| P13 | `POST /warehouses/{id}/slotting/runs` | T31 | `slotting/analysis.py` | all | contiguous access, `float32`, no copies |
| P14 | CLI `parcelpilot-worker` | T41 | `cli/worker.py` | startup profile | lazy imports |

---

# Open questions

1. **T23:** which profile formats does your pipeline already consume, and does it get call counts?
2. **Hardware:** can your CI machine hold the `hostile` workload (about 5M shipment events, 2M import rows)? If not, lower the volumes or rely on `--scale`.
3. **Handler style (T03):** OK with mostly sync `def` handlers and only `login` and `health` as `async def`? Making more handlers async would spread the P9 stall to more endpoints.
4. **P10 scope:** is "no change" an acceptable analyzer answer for bcrypt and gzip/HMAC, or do you want it flagged for review instead?
