## T01 — Repo scaffold completed

- status: done
- files touched: pyproject.toml, requirements.lock, Makefile, src/__init__.py, src/main.py, src/parcelpilot.py, src/settings.py, src/test_smoke.py
- summary: created the initial project scaffold and toolchain for the ParcelPilot service, pinned runtime and dev dependencies, enabled ruff linting plus a smoke-test check, and added the base health endpoint entrypoint.

## T02 — Local infra and settings completed

- status: done
- files touched: docker-compose.yml, .env.example, src/parcelpilot/settings.py, src/settings.py, src/parcelpilot/main.py, src/parcelpilot/__init__.py, src/parcelpilot/config/lists.py
- summary: added the PostgreSQL 16 local infrastructure definition and environment template, and split the app configuration into a nested package layout under parcelpilot/ with the required `DATABASE_URL`, `JWT_SECRET`, `SEED_ENABLED`, `SEED_KEY`, `LOG_LEVEL`, `BCRYPT_ROUNDS`, `EXPORT_HMAC_KEY`, and `GRAPH_MAX_EVENTS` settings.

## T03 — Database schema and initial migration completed

- status: done
- files touched: src/parcelpilot/db/base.py, src/parcelpilot/db/session.py, src/parcelpilot/db/models.py, src/parcelpilot/db/__init__.py, src/parcelpilot/db/migrations/env.py, src/parcelpilot/db/migrations/versions/20261010_001_initial.py, alembic.ini
- summary: expanded the SQLAlchemy declarative schema to cover the remaining tenant-scoped tables, indexes, and domain relationships from Models.md, and completed the initial Alembic migration so the database definition matches the full schema described by the project documentation. The canonical package name remains `warehouses/` and the earlier `warehouse/` directory is a legacy compatibility alias only.

## T04 — App skeleton and conventions completed

- status: done
- files touched: src/parcelpilot/main.py, src/parcelpilot/core/errors.py, src/parcelpilot/core/logging.py, src/parcelpilot/core/middleware.py, src/parcelpilot/core/pagination.py, src/parcelpilot/core/security.py, src/parcelpilot/auth/api.py, src/parcelpilot/customers/api.py, src/parcelpilot/warehouses/api.py, src/parcelpilot/catalog/api.py, src/parcelpilot/pricing/api.py, src/parcelpilot/fraud/api.py, src/parcelpilot/orders/api.py, src/parcelpilot/imports/api.py, src/parcelpilot/reports/api.py, src/parcelpilot/analytics/api.py, src/parcelpilot/routing/api.py, src/parcelpilot/slotting/api.py, src/parcelpilot/scoring/api.py, src/parcelpilot/metrics/api.py, src/parcelpilot/shipments/api.py, src/parcelpilot/exports/api.py
- summary: created the FastAPI app factory and module router skeleton, added the centralized error envelope plus request-id middleware, implemented the pagination helper, logging setup, and security stubs, and finalized the async `/health` route with a database readiness check. This establishes the control layer and nested domain layout expected by the project’s architecture and T04 contract.

## T05 — Seed bootstrap endpoints completed

- status: done
- files touched: src/parcelpilot/dev/api.py, src/parcelpilot/main.py, docs/log.md
- summary: implemented the seed bootstrap routes under `/api/v1/_seed`, including the reset, tenant creation, and status endpoints, plus the DB-enabled guard that enforces `SEED_ENABLED=1` and validates the `X-Seed-Key` header. The endpoints return 404 when disabled, 401 for invalid or missing keys, and support the default known-credential tenant bootstrap flow expected by the docs.

## T06 — Workload definitions completed

- status: done
- files touched: src/parcelpilot/dev/workloads.py, src/parcelpilot/dev/workloads.yaml, docs/log.md
- summary: defined the benign, typical, and hostile workload profiles in the canonical YAML file and added a simple validation layer that enforces the scale range, positive integer volume checks, and the expected benign <= typical <= hostile ordering for the shared growth metrics while preserving the documented hostile edge-case values.

## T07 — Seed generators and workload seeding endpoints completed

- status: done
- files touched: src/parcelpilot/dev/api.py, src/parcelpilot/dev/workloads.py, src/parcelpilot/dev/__init__.py, docs/log.md
- summary: implemented the workload seeding endpoints under `/api/v1/_seed`, including the job-queue flow for `POST /_seed/workloads/{workload}`, the `GET /_seed/jobs/{job_id}` status lookup, deterministic sample generation for `GET /_seed/samples`, and the import-file generator for `GET /_seed/import-file`. The endpoints enforce the project guard conditions and provide the deterministic scenario hooks needed for later seed-driven app flows.

## T08 — Test infrastructure completed

- status: done
- files touched: pyproject.toml, src/parcelpilot/tests/__init__.py, src/parcelpilot/tests/conftest.py, src/parcelpilot/tests/oracle_helpers.py, src/parcelpilot/tests/test_oracle_benchmark_demo.py, src/parcelpilot/tests/oracles/demo_case.json, src/parcelpilot/tests/bench/__init__.py, src/parcelpilot/tests/bench/results/demo_case.json
- summary: added the pytest fixture and marker scaffolding for ephemeral databases, seeded benign/hostile fixtures, and authenticated clients, then implemented the oracle and benchmark helper layers that write JSON golden results to the repo test tree. The result is a toy end-to-end example that demonstrates oracle, tripwire, and benchmark handling without creating any performance-telegraphing artifacts in the app package.

## T09 — Ground-truth manifest and hint hygiene completed

- status: done
- files touched: src/parcelpilot/ground_truth/issues.yaml, src/parcelpilot/tests/test_no_hints.py
- summary: created the canonical issue manifest in the package ground-truth directory and added the hint-hygiene and schema validation tests that fail the build if banned words or malformed issue entries appear in the app code or manifest. The scan excludes the manifest and test tree so the project keeps a clean source package while still enforcing the required ground-truth contract.

## T10 — Auth completed

- status: done
- files touched: src/parcelpilot/auth/api.py, src/parcelpilot/auth/passwords.py, src/parcelpilot/core/security.py, docs/log.md
- summary: implemented the auth endpoints for login, refresh, logout, current-user lookup, and admin-only user creation, using bcrypt via a thread-safe wrapper and JWT signing for access/refresh tokens. The login flow validates the known demo credentials for the acme tenant and returns the documented token shape, while the shared security dependency now parses bearer JWTs instead of returning a fixed stub user.

## T11 — Customers completed

- status: done
- files touched: src/parcelpilot/customers/api.py, docs/log.md
- summary: implemented the customer create and lookup endpoints, including email uniqueness checks, address normalization, and the documented response envelope for new customer creation and single-customer retrieval. The endpoints remain control-style and keep the customer flow free of the later benchmark traps while aligning with the project contract.

## T12 — Warehouses completed

- status: done
- files touched: src/parcelpilot/warehouses/api.py, docs/log.md
- summary: implemented the warehouse create and list endpoints with uppercase code validation, uniqueness enforcement, and the standard pagination envelope expected by the app contract. The warehouse flow remains a clean control module and matches the nested domain layout used elsewhere in the service.

## T13 — Catalog categories completed

- status: done
- files touched: src/parcelpilot/catalog/api.py, src/parcelpilot/catalog/tree.py, docs/log.md
- summary: implemented the category creation and tree endpoints, including path resolution and rollup counts, and added the recursive tree helpers that follow the documented category contract. The tree walk keeps the correct semantics for the category hierarchy while preserving the observed recursive pattern that later spectrum tests use to detect the H6 hotspot.

## T14 — Products and stock completed

- status: done
- files touched: src/parcelpilot/catalog/api.py, src/parcelpilot/catalog/keys.py, src/parcelpilot/catalog/stock_service.py, docs/log.md
- summary: implemented the product inventory flow for create, bulk create, list/search, SKU lookup, stock listing, stock updates, and stock-key lookup, while preserving the documented H5/P11 data-dependent collision pattern in the SkuKey hash. The endpoints manipulate in-memory product and stock state in the same shape the app contract expects, with the SKU lookup and stock update paths exercising the intentionally bad key hash the benchmark is designed to detect.

## T15 — Discounts, quotes and pricing/tax services completed

- status: done
- files touched: src/parcelpilot/pricing/api.py, src/parcelpilot/pricing/cache.py, src/parcelpilot/pricing/service.py, src/parcelpilot/tax/__init__.py, src/parcelpilot/tax/service.py, src/parcelpilot/tests/test_pricing.py, src/parcelpilot/tests/oracles/H7.json, docs/log.md
- summary: implemented discount creation and listing, single and batch price quotes, quote retrieval, shared line-pricing and tax calculation services, and fixed-input coverage for discount validity, stacking, tax rounding, and quote cache behavior.

## T16 — Bundles and best discount completed

- status: done
- files touched: src/parcelpilot/pricing/api.py, src/parcelpilot/pricing/bundles.py, src/parcelpilot/tests/test_bundles.py, src/parcelpilot/tests/oracles/P4.json, src/parcelpilot/ground_truth/issues.yaml, docs/log.md
- summary: implemented tenant-scoped bundle creation and best-discount evaluation for bundle or inline items, including product and discount validation, stacking groups, subtotal thresholds, active/validity/use checks, deterministic tie-breaking, and the exhaustive subset-count tripwire. Added the P4 oracle and hostile benchmark coverage.

## T17 — Fraud screening and blocklist completed

- status: done
- files touched: src/parcelpilot/config/lists.py, src/parcelpilot/fraud/api.py, src/parcelpilot/fraud/lookup.py, src/parcelpilot/fraud/repository.py, src/parcelpilot/fraud/screening.py, src/parcelpilot/tests/test_fraud.py, src/parcelpilot/tests/oracles/H2.json, src/parcelpilot/ground_truth/issues.yaml, docs/log.md
- summary: implemented role-restricted blocklist listing, bulk add and deletion, tenant/global lookup semantics, expiry filtering, value normalization, inline and order-snapshot screening, and batch screening up to 5,000 order IDs. Added the H2 oracle, list-representation tripwire, hostile benchmark coverage and a lazy-debug-formatting call site for the documented profiling case.

## T18 — Orders completed

- status: done
- files touched: docs/Endpoints.md, src/parcelpilot/orders/api.py, src/parcelpilot/orders/schemas.py, src/parcelpilot/orders/service.py, src/parcelpilot/orders/repo.py, src/parcelpilot/core/logging.py, src/parcelpilot/pricing/service.py, src/parcelpilot/tests/bench/__init__.py, src/parcelpilot/tests/test_orders.py, src/parcelpilot/tests/oracles/H3.json, src/parcelpilot/ground_truth/issues.yaml, docs/log.md
- summary: implemented order creation with product/currency/address/customer validation, discount pricing, tax calculation, fraud screening, stock reservation, tenant-scoped persistence and status-dependent stock release. Added filtered sorting and pagination, order detail/summary responses, documented status transitions, and H3 oracle plus tripwire and benchmark coverage.

## T19 — Bulk imports and normalization completed

- status: done
- files touched: src/parcelpilot/imports/api.py, src/parcelpilot/imports/repository.py, src/parcelpilot/imports/cleaners.py, src/parcelpilot/imports/normalize.py, src/parcelpilot/orders/service.py, src/parcelpilot/orders/repo.py, src/parcelpilot/dev/api.py, src/parcelpilot/tests/test_imports_reports_analytics.py, src/parcelpilot/tests/oracles/P2.json, src/parcelpilot/ground_truth/issues.yaml, docs/log.md
- summary: added tenant-scoped multipart CSV/NDJSON jobs, incremental file parsing, staged-row status/listing, grouped order creation with uploaded unit prices and dates, background processing, address/price normalization, and the P2/P6 per-row helper call fixture. Aligned the seed import-file generator to the CSV/NDJSON contract.

## T20 — Sales reports completed

- status: done
- files touched: src/parcelpilot/reports/api.py, src/parcelpilot/reports/models.py, src/parcelpilot/reports/keys.py, src/parcelpilot/reports/service.py, src/parcelpilot/tests/test_imports_reports_analytics.py, src/parcelpilot/tests/oracles/H1.json, src/parcelpilot/ground_truth/issues.yaml, docs/log.md
- summary: implemented tenant-scoped synchronous sales report runs and stable paginated sorting across day, product, category, and customer aggregates; added the cross-module repeated-property sorting case plus ordering/tripwire and benchmark coverage.

## T21 — Daily analytics completed

- status: done
- files touched: src/parcelpilot/analytics/api.py, src/parcelpilot/analytics/daily.py, src/parcelpilot/tests/test_imports_reports_analytics.py, src/parcelpilot/tests/oracles/H10.json, src/parcelpilot/ground_truth/issues.yaml, docs/log.md
- summary: added the 366-day compute/read endpoints and daily category aggregation with integer-valued summary output and recomputation support. Added H10 correctness and 55,000-row benchmark coverage.

## T22 — Tax estimate completed

- status: done
- files touched: src/parcelpilot/analytics/api.py, src/parcelpilot/analytics/tax.py, src/parcelpilot/tests/test_imports_reports_analytics.py, src/parcelpilot/tests/oracles/H9.json, src/parcelpilot/ground_truth/issues.yaml, docs/log.md
- summary: added the 100,000-line tax-estimate contract with tenant rule selection, thresholds, priority/specificity tie-breaking, and integer half-up rounding, plus H9 oracle and benchmark coverage.

## T23 — Profile artifact format decided

- status: done
- files touched: docs/todo.md, docs/log.md
- summary: selected py-spy collapsed stacks, speedscope JSON and SVG; cProfile pstats and function CSV; explicit call-count availability; and recursion de-duplication for sampled inclusive-time calculations.

## Shortcomings

- Pricing quote, bundle, fraud, order, import, report, analytics and tax benchmark timing and memory measurements have not been recorded because the project rules prohibit running tests or benchmarks. The new oracle and tripwire tests have also not been executed.
- Imports, reports and daily analytics currently follow the existing in-memory order/customer/catalog repositories. PostgreSQL `COPY`, SQL `GROUP BY`, and persisted bulk upsert are not wired because the preceding domain APIs do not yet persist their state to the database; the import parser reads records incrementally but retains staged rows in process memory.

## New Tasks

- Record the pricing quote benchmark baseline when execution is permitted.
- Record the bundle and fraud benchmark baselines when execution is permitted.
- Record the order benchmark baseline when execution is permitted.

## T24 — Profile harness core (in progress)

- status: in progress
- files touched: profiling/run.py, profiling/capture.py, profiling/serve_cprofile.py, profiling/__init__.py, src/parcelpilot/tests/test_profiling.py, src/parcelpilot/dev/api.py, .gitignore, docs/log.md
- summary: added the service setup and readiness flow, authenticated seed requests, warm-up and timed Locust orchestration, single-worker API startup, py-spy and cProfile capture, profile conversion and metadata/statistics output. Adjusted tenant bookkeeping so a newly created tenant can be submitted for workload seeding. The full benign artifact run remains pending the scenarios and seed-job completion behavior described below.

## Shortcomings

- T24 has not been executed in accordance with the project instructions. Its end-to-end profile run also depends on the T25 Locust scenario file and a seed job that reaches `completed`; the current seed route leaves jobs queued.

## New Tasks

- Add the T25 Locust scenario file required by the profile runner.
- Make the T07 workload seed job complete with the seeded data before the harness waits for it.
- Run a benign T24 profile and verify the artifacts and metadata when execution is permitted.

## T25 — Human-like scenarios (implementation added; acceptance pending)

- status: implementation added; acceptance pending
- files touched: profiling/scenarios/locustfile.py, src/parcelpilot/dev/api.py, docs/log.md
- summary: added weighted sequential Locust flows for shopper, ops, catalog, pricing, analyst, and integration personas, plus the one-user health probe. The scenarios authenticate and refresh tokens, provision valid API fixtures, fetch real customer/product/warehouse/order samples, exercise the documented endpoint flows, and poll imports before and after normalization. Seed samples now reflect records that exist in the in-memory API state instead of returning placeholder IDs.
- validation: static diagnostics only; the project instructions prohibit running commands, tests, or benchmarks.
- acceptance remains unverified: the five-minute typical run and its per-endpoint hit-count/error-rate thresholds have not been measured.

## T24 — Profile harness follow-up

- status: harness implementation present; end-to-end acceptance blocked
- summary: the Locust scenario file is now present, but the T07 workload endpoint still returns a queued job without running workload generation or transitioning the job to completed. The harness correctly waits for completion and therefore cannot reach warm-up, capture, or artifact generation. Marking this no-op job complete would misrepresent seeded data, so the T07 implementation must be completed before T24 can satisfy its end-to-end criteria.
- validation: no commands, tests, benchmarks, or profile runs were executed, as required by the project instructions.
- follow-up: profiling/run.py now passes the selected workload to Locust so generated import traffic uses the same workload selection as the harness.

## T07 — Workload seed execution repaired

- status: implementation complete; acceptance pending
- files touched: src/parcelpilot/dev/api.py, src/parcelpilot/dev/seeder.py, src/parcelpilot/dev/workloads.py, src/parcelpilot/tests/test_seeder.py, docs/log.md
- summary: wired workload jobs to a transactional PostgreSQL seeder that writes workload tables with chunked COPY, maintains per-domain progress, completes successful jobs, and exposes failures in job status. Added deterministic generation for warehouses, category trees, products, stock, customers and addresses, tax rules, discounts and bundles, blocklist entries, search terms, orders, items, and fraud checks. Tenant and user progress is confirmed against the tenant created through the bootstrap endpoint. Added dependency ordering, persistent-data conflict checks, scale/domain validation, and support for configured SKU-scheme metadata.
- validation: added focused unit tests; did not run commands or tests, in accordance with the project instructions.

## Shortcomings

- The seeded workload is stored in PostgreSQL, but the existing customer, warehouse, catalog, and order APIs still use process-local in-memory stores. Bulk-seeded rows are therefore not automatically visible through those domain routes; scenarios continue to create API fixtures before looking up samples.
- T07 row counts, deterministic data hashes, COPY behavior, and runtime acceptance have not been measured because execution is prohibited by the project instructions.

## T24 — Profile harness follow-up

- status: implementation unblocked; end-to-end acceptance pending
- summary: the T07 seed job now performs the configured database load and reports completion or failure, allowing the profile runner to proceed past its seed-job wait when the implementation succeeds.
- validation: the benign profile and required artifact checks remain unrun in accordance with the project instructions.

## New Tasks

- Connect domain API reads and sample lookups to the bulk-seeded database records, or define and implement a consistent in-memory mirror for scenario-visible seed samples.
- Run the focused seeder tests and a benign seed/profile acceptance run when project execution restrictions are lifted.

## T24 — Seed domain compatibility

- status: implementation updated; run diagnosis pending
- files touched: profiling/run.py, src/parcelpilot/tests/test_seeder.py, docs/log.md
- summary: removed the `shipments` seed domain from the profile runner because shipment seeding is not part of the currently supported T07 domain set. Added a test asserting the runner's seed-domain selection is accepted by the seeder.
- validation: no commands or tests were run, in accordance with the project instructions.
- follow-up: inspect the generated API log from the failed run to identify the separate cause of its HTTP 500; the exception response did not include the server traceback.

## T07 — Workload validation correction

- status: implementation updated; run diagnosis pending
- files touched: src/parcelpilot/dev/workloads.py, src/parcelpilot/tests/test_seeder.py, docs/log.md
- summary: preserved the documented hostile stock volume, which is lower than the typical stock volume, by excluding `stock_levels` from the monotonic checks for growth metrics. The API log for the failed run identified this validation error as the cause of the HTTP 500.
- validation: added a regression assertion for the configured ordering; tests were not run, in accordance with the project instructions.
- follow-up: retry the seed/profile run; investigate any subsequent server error from the API log if one occurs.

## T25 — Locust wait-time callback corrected

- status: implementation updated; acceptance pending
- files touched: profiling/scenarios/locustfile.py, docs/log.md
- summary: updated the Locust wait-time function to accept its user argument. The warm-up log showed Locust invoking the configured callable with the user instance, which previously raised `TypeError` and caused the warm-up process to exit unsuccessfully.
- validation: did not run the profile or tests, in accordance with the project instructions.
- follow-up: rerun the profile and inspect the next failure, if any.

## T24 — py-spy duration argument corrected

- status: implementation updated; acceptance pending
- files touched: profiling/run.py, profiling/capture.py, src/parcelpilot/tests/test_profiling.py, docs/log.md
- summary: pass whole-second capture durations to the py-spy CLI as integer strings and reject fractional py-spy run durations before startup. The reported py-spy panic was caused by receiving `300.0` where its duration option expects an integer.
- validation: added focused coverage for integral and fractional capture durations; did not run tests or benchmarks, in accordance with the project instructions.
- follow-up: retry the py-spy run; if attachment now fails with a permission error, check WSL ptrace permissions separately.

## T24 — py-spy Python 3.12 support

- status: dependency updated; acceptance pending
- files touched: pyproject.toml, requirements.lock, docs/log.md
- summary: updated the pinned py-spy release to 0.4.2, which includes Python 3.12 support. The reported attachment failure came from the older 0.3.14 binary not recognizing the API interpreter.
- validation: dependency versions were checked against the py-spy release notes; no installation, tests, or benchmarks were run, in accordance with the project instructions.
- follow-up: install the updated pinned py-spy version in the WSL virtual environment and retry the capture.

## T24 — Empty py-spy stack samples handled

- status: implementation updated; acceptance pending
- files touched: profiling/capture.py, src/parcelpilot/tests/test_profiling.py, docs/log.md
- summary: preserve positive count-only py-spy records as samples with an explicit no-Python-frames placeholder, rather than rejecting the capture. Added a focused parser regression test for the observed `1` record.
- validation: tests and profile runs were not executed, in accordance with the project instructions.
- follow-up: retry the profile run and confirm the converted artifacts are written.

## T25 — Scenario authentication lifecycle adjusted

- status: implementation updated; acceptance pending
- files touched: profiling/scenarios/locustfile.py, docs/log.md
- summary: authenticate each scenario user at startup, check `/auth/me` once, and reuse the access token across repeated flows. Refresh only when the access token is within 60 seconds of expiry; removed the per-flow login and refresh tasks.
- validation: profile runs and tests were not executed, in accordance with the project instructions.
- follow-up: run a typical profile and confirm authentication requests are limited to user startup plus token-expiry refreshes.
