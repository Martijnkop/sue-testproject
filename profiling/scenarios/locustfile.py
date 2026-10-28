from __future__ import annotations

import csv
import io
import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from locust import HttpUser, SequentialTaskSet, constant, task

API = "/api/v1"
SEED_KEY = os.environ.get("PARCELPILOT_SEED_KEY", "")
TENANT_SLUG = os.environ.get("PARCELPILOT_TENANT_SLUG", "acme")
PASSWORD = os.environ.get("PARCELPILOT_PASSWORD", "Password123!")
ADMIN_USERNAME = os.environ.get("PARCELPILOT_USERNAME", "admin@acme.example")
WORKLOAD = os.environ.get("PARCELPILOT_WORKLOAD", "typical")
SUSPICIOUS_IP = "203.0.113.42"


def _think_time(_user: Any) -> float:
    return min(8.0, max(1.0, random.lognormvariate(1.0, 0.45)))


def _unique(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:12].upper()}"


class ScenarioUser(HttpUser):
    abstract = True
    wait_time = _think_time
    role_username = ""

    def on_start(self) -> None:
        self._sequence = 0
        self._access_token_expires_at = 0.0
        self.authenticate()
        self._required("GET", f"{API}/auth/me", name="/auth/me")
        self._create_fixture()

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200, 201, 202, 204),
        name: str | None = None,
    ) -> dict[str, Any] | None:
        if path not in {f"{API}/auth/login", f"{API}/auth/refresh"}:
            self._ensure_authentication()
        request_headers = headers or {}
        with self.client.request(
            method,
            path,
            json=payload,
            params=params,
            headers=request_headers,
            files=files,
            data=data,
            name=name,
            catch_response=True,
        ) as response:
            if response.status_code in {409, 422}:
                response.success()
                try:
                    result = response.json()
                except ValueError:
                    return None
                return result if isinstance(result, dict) else None
            if response.status_code not in expected:
                response.failure(f"Unexpected HTTP {response.status_code}: {response.text[:300]}")
                return None
            response.success()
            if response.status_code == 204 or not response.content:
                return None
            try:
                result = response.json()
            except ValueError as error:
                response.failure(f"Expected a JSON response: {error}")
                return None
            if not isinstance(result, dict):
                response.failure("Expected a JSON object response")
                return None
            return result

    def _required(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        response = self._request(*args, **kwargs)
        if response is None:
            raise RuntimeError(f"Required scenario request failed: {args[0]} {args[1]}")
        return response

    def authenticate(self) -> None:
        username = self.role_username or ADMIN_USERNAME
        token = self._required(
            "POST",
            f"{API}/auth/login",
            data={
                "username": username,
                "password": PASSWORD,
                "tenant_slug": TENANT_SLUG,
            },
            name="/auth/login",
        )
        self._access_token_expires_at = time.monotonic() + int(token["expires_in"])
        self.refresh_token = str(token["refresh_token"])
        self.client.headers["Authorization"] = f"Bearer {token['access_token']}"

    def refresh_authentication(self) -> None:
        token = self._required(
            "POST",
            f"{API}/auth/refresh",
            payload={"refresh_token": self.refresh_token},
            name="/auth/refresh",
        )
        self._access_token_expires_at = time.monotonic() + int(token["expires_in"])
        self.refresh_token = str(token["refresh_token"])
        self.client.headers["Authorization"] = f"Bearer {token['access_token']}"

    def _ensure_authentication(self) -> None:
        if self._access_token_expires_at == 0.0:
            raise RuntimeError("Scenario request attempted before authentication")
        if time.monotonic() >= self._access_token_expires_at - 60:
            self.refresh_authentication()

    def _samples(self, kind: str) -> list[Any]:
        response = self._required(
            "GET",
            f"{API}/_seed/samples",
            params={"kind": kind, "n": 500},
            headers={"X-Seed-Key": SEED_KEY},
            name=f"/_seed/samples?kind={kind}",
        )
        return list(response.get("items", []))

    def _create_fixture(self) -> None:
        category = self._required(
            "POST",
            f"{API}/catalog/categories",
            payload={"name": "Scenario Goods", "slug": _unique("scenario-").lower()},
            name="/catalog/categories",
        )
        category_id = int(category["id"])
        for depth in range(4):
            child = self._required(
                "POST",
                f"{API}/catalog/categories",
                payload={
                    "name": f"Scenario Goods {depth + 1}",
                    "slug": _unique("scenario-").lower(),
                    "parent_id": category_id,
                },
                name="/catalog/categories",
            )
            category_id = int(child["id"])
        warehouse = self._required(
            "POST",
            f"{API}/warehouses",
            payload={"code": _unique("W")[:12], "name": "Scenario Warehouse", "region": "DE"},
            name="/warehouses",
        )
        self.customer_email = f"{_unique('scenario').lower()}@example.com"
        customer = self._required(
            "POST",
            f"{API}/customers",
            payload={
                "email": self.customer_email,
                "full_name": "Scenario Customer",
                "addresses": [
                    {
                        "line1": "1 Scenario Street",
                        "city": "Leipzig",
                        "postal_code": "04229",
                        "country_code": "DE",
                        "is_default": True,
                    }
                ],
            },
            name="/customers",
        )
        self.warehouse_code = str(warehouse["code"])
        self.customer_id = int(customer["id"])
        self.sku = _unique("SKU")
        self._required(
            "POST",
            f"{API}/catalog/products",
            payload={
                "sku": self.sku,
                "name": "Scenario Product",
                "category_id": category_id,
                "base_price_cents": 2499,
                "currency": "EUR",
            },
            name="/catalog/products",
        )
        self._required(
            "PUT",
            f"{API}/catalog/stock",
            payload={
                "mode": "set",
                "updates": [{"warehouse_code": self.warehouse_code, "sku": self.sku, "quantity": 100}],
            },
            name="/catalog/stock",
        )

        customer_ids = self._samples("customer_ids")
        product_skus = self._samples("product_skus")
        warehouse_ids = self._samples("warehouse_ids")
        if not customer_ids or not product_skus or not warehouse_ids:
            raise RuntimeError("Scenario fixture records were not returned by /_seed/samples")
        self.customer_id = int(customer_ids[-1])
        self.sku = str(product_skus[-1])
        warehouse_id = int(warehouse_ids[-1])
        customer_record = self._required(
            "GET",
            f"{API}/customers/{self.customer_id}",
            name="/customers/[customer_id]",
        )
        self.customer_email = str(customer_record["email"])
        warehouses = self._required(
            "GET",
            f"{API}/warehouses",
            name="/warehouses",
        )
        warehouse_record = next(
            (item for item in warehouses.get("items", []) if int(item["id"]) == warehouse_id),
            None,
        )
        if warehouse_record is None:
            raise RuntimeError("Sample warehouse ID was not found in the warehouse list")
        self.warehouse_code = str(warehouse_record["code"])
        self._sequence = 0

    def _poll_import(self, job_id: int) -> dict[str, Any]:
        for _ in range(20):
            job = self._required(
                "GET",
                f"{API}/imports/{job_id}",
                name="/imports/[job_id]",
            )
            if job["status"] == "completed":
                return job
            if job["status"] == "failed":
                raise RuntimeError(f"Scenario import job failed: {job!r}")
            time.sleep(0.1)
        raise RuntimeError(f"Scenario import job {job_id} did not complete")

    def _create_order(self, *, client_ip: str | None = None) -> dict[str, Any]:
        self._sequence += 1
        self._required(
            "PUT",
            f"{API}/catalog/stock",
            payload={
                "mode": "set",
                "updates": [{"warehouse_code": self.warehouse_code, "sku": self.sku, "quantity": 100}],
            },
            name="/catalog/stock",
        )
        return self._required(
            "POST",
            f"{API}/orders",
            payload={
                "customer_id": self.customer_id,
                "external_ref": _unique("order-"),
                "currency": "EUR",
                "client_ip": client_ip,
                "items": [{"sku": self.sku, "quantity": 1}],
                "shipping_address": {
                    "line1": "1 Scenario Street",
                    "city": "Leipzig",
                    "postal_code": "04229",
                    "country_code": "DE",
                },
            },
            name="/orders",
        )


class ShopperFlow(SequentialTaskSet):
    @task
    def browse_search_and_stock(self) -> None:
        self.user._required(
            "GET",
            f"{API}/catalog/products",
            params={"q": "Scenario", "limit": 20},
            name="/catalog/products",
        )
        self.user._required(
            "GET",
            f"{API}/catalog/products/{self.user.sku}",
            name="/catalog/products/[sku]",
        )
        self.user._required(
            "POST",
            f"{API}/catalog/stock/lookup",
            payload={"keys": [{"warehouse_code": self.user.warehouse_code, "sku": self.user.sku}]},
            name="/catalog/stock/lookup",
        )

    @task
    def quote_and_order(self) -> None:
        quote = self.user._required(
            "POST",
            f"{API}/pricing/quotes",
            payload={
                "sku": self.user.sku,
                "quantity": 1,
                "customer_id": self.user.customer_id,
                "currency": "EUR",
            },
            name="/pricing/quotes",
        )
        self.user._required(
            "GET",
            f"{API}/pricing/quotes/{quote['quote_id']}",
            name="/pricing/quotes/[quote_id]",
        )
        customer = self.user._required(
            "GET",
            f"{API}/customers/{self.user.customer_id}",
            name="/customers/[customer_id]",
        )
        order = self.user._create_order()
        self.user._required(
            "GET",
            f"{API}/orders/{order['id']}",
            name="/orders/[order_id]",
        )
        if self.user._sequence % 3 == 0:
            self.user._required(
                "POST",
                f"{API}/customers",
                payload={
                    "email": _unique("optional").lower() + "@example.com",
                    "full_name": customer["full_name"],
                },
                name="/customers",
            )


class OpsFlow(SequentialTaskSet):
    @task
    def manage_orders(self) -> None:
        self.user._required(
            "GET",
            f"{API}/orders",
            params={"status": "pending", "limit": 50, "sort": "-placed_at"},
            name="/orders",
        )
        order = self.user._create_order(client_ip=SUSPICIOUS_IP)
        self.user._required("GET", f"{API}/orders/{order['id']}", name="/orders/[order_id]")
        self.user._required(
            "POST",
            f"{API}/fraud/screen",
            payload={"order_id": order["id"]},
            name="/fraud/screen",
        )
        self.user._required(
            "POST",
            f"{API}/fraud/screen/batch",
            payload={"order_ids": [order["id"]]},
            name="/fraud/screen/batch",
        )
        self.user._required(
            "PATCH",
            f"{API}/orders/{order['id']}/status",
            payload={"status": "confirmed", "reason": "Order reviewed"},
            name="/orders/[order_id]/status",
        )


class CatalogFlow(SequentialTaskSet):
    @task
    def browse_and_update_catalog(self) -> None:
        self.user._required(
            "GET",
            f"{API}/catalog/categories",
            params={"tree": "false", "max_depth": 10},
            name="/catalog/categories",
        )
        product = self.user._required(
            "GET",
            f"{API}/catalog/products/{self.user.sku}",
            name="/catalog/products/[sku]",
        )
        category_id = int(product["category_id"])
        self.user._required(
            "GET",
            f"{API}/catalog/categories/{category_id}/path",
            name="/catalog/categories/[category_id]/path",
        )
        self.user._required(
            "GET",
            f"{API}/catalog/categories/{category_id}/rollup",
            name="/catalog/categories/[category_id]/rollup",
        )
        sku = _unique("BULK")
        self.user._required(
            "POST",
            f"{API}/catalog/products/bulk",
            params={"on_conflict": "skip"},
            payload={
                "products": [
                    {
                        "sku": sku,
                        "name": "Bulk Scenario Product",
                        "category_id": category_id,
                        "base_price_cents": 1299,
                        "currency": "EUR",
                    }
                ]
            },
            name="/catalog/products/bulk",
        )
        self.user._required(
            "PUT",
            f"{API}/catalog/stock",
            payload={
                "mode": "delta",
                "updates": [{"warehouse_code": self.user.warehouse_code, "sku": sku, "quantity": 5}],
            },
            name="/catalog/stock",
        )
        self.user._required(
            "POST",
            f"{API}/catalog/stock/lookup",
            payload={"keys": [{"warehouse_code": self.user.warehouse_code, "sku": sku}]},
            name="/catalog/stock/lookup",
        )


class PricingFlow(SequentialTaskSet):
    @task
    def price_bundle(self) -> None:
        code = _unique("DISC")
        self.user._required(
            "POST",
            f"{API}/pricing/discounts",
            payload={
                "discounts": [
                    {"code": code, "kind": "percent", "value": 1000, "stack_group": code}
                ]
            },
            name="/pricing/discounts",
        )
        discounts = self.user._required(
            "GET",
            f"{API}/pricing/discounts",
            params={"is_active": "true", "limit": 100},
            name="/pricing/discounts",
        )
        discount = next(item for item in discounts["items"] if item["code"] == code)
        bundle = self.user._required(
            "POST",
            f"{API}/pricing/bundles",
            payload={
                "name": _unique("Scenario Bundle"),
                "items": [{"sku": self.user.sku, "quantity": 1}],
                "discount_ids": [discount["id"]],
            },
            name="/pricing/bundles",
        )
        self.user._required(
            "POST",
            f"{API}/pricing/bundles/best-discount",
            payload={
                "bundle_id": bundle["id"],
                "candidate_discount_ids": [discount["id"]],
                "max_stacked": 3,
            },
            name="/pricing/bundles/best-discount",
        )


class AnalystFlow(SequentialTaskSet):
    @task
    def analyze_sales_and_tax(self) -> None:
        report = self.user._required(
            "POST",
            f"{API}/reports/sales",
            payload={"group_by": "product", "currency": "EUR", "top_n": 100},
            name="/reports/sales",
        )
        self.user._required(
            "GET",
            f"{API}/reports/sales/{report['run_id']}/rows",
            params={"sort_by": "revenue_cents", "order": "desc", "limit": 50},
            name="/reports/sales/[run_id]/rows",
        )
        self.user._required(
            "GET",
            f"{API}/reports/sales/{report['run_id']}/rows",
            params={"sort_by": "label", "order": "asc", "limit": 50},
            name="/reports/sales/[run_id]/rows",
        )
        today = datetime.now(timezone.utc).date()
        date_from = (today - timedelta(days=90)).isoformat()
        date_to = today.isoformat()
        self.user._required(
            "POST",
            f"{API}/analytics/daily/compute",
            payload={
                "date_from": date_from,
                "date_to": date_to,
                "currency": "EUR",
                "recompute": True,
            },
            name="/analytics/daily/compute",
        )
        self.user._required(
            "GET",
            f"{API}/analytics/daily",
            params={"date_from": date_from, "date_to": date_to, "currency": "EUR"},
            name="/analytics/daily",
        )
        self.user._required(
            "POST",
            f"{API}/analytics/tax/estimate",
            payload={"country_code": "DE", "region": "SN", "lines": [{"amount_cents": 2499}]},
            name="/analytics/tax/estimate",
        )


class IntegratorFlow(SequentialTaskSet):
    @task
    def import_orders(self) -> None:
        with self.client.get(
            f"{API}/_seed/import-file",
            params={"workload": WORKLOAD, "rows": 1, "bad_row_pct": 0, "format": "csv"},
            headers={"X-Seed-Key": SEED_KEY},
            name="/_seed/import-file",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Unexpected HTTP {response.status_code}: {response.text[:300]}")
                return
            response.success()
            rows = list(csv.DictReader(io.StringIO(response.text)))
        if not rows:
            raise RuntimeError("Seed import-file endpoint returned no CSV rows")
        rows[0].update(
            {
                "external_ref": _unique("import-"),
                "customer_email": self.user.customer_email,
                "sku": self.user.sku,
                "quantity": "1",
                "currency": "EUR",
                "unit_price": "24.99",
            }
        )
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        uploaded = self.user._required(
            "POST",
            f"{API}/imports/orders",
            files={"file": ("scenario.csv", output.getvalue(), "text/csv")},
            data={"format": "csv", "dry_run": "false", "default_currency": "EUR", "batch_size": "1"},
            name="/imports/orders",
        )
        job_id = int(uploaded["job_id"])
        self.user._poll_import(job_id)
        self.user._required(
            "GET",
            f"{API}/imports/{job_id}/rows",
            params={"limit": 10, "offset": 0},
            name="/imports/[job_id]/rows",
        )
        self.user._required(
            "POST",
            f"{API}/imports/{job_id}/normalize",
            payload={"normalize_addresses": True, "normalize_prices": True},
            expected=(202,),
            name="/imports/[job_id]/normalize",
        )
        self.user._poll_import(job_id)
        order_ids = self.user._samples("order_ids")
        if not order_ids:
            raise RuntimeError("No real order IDs were returned after importing an order")
        self.user._required(
            "POST",
            f"{API}/fraud/screen/batch",
            payload={"order_ids": [int(order_ids[-1])]},
            name="/fraud/screen/batch",
        )


class Shopper(ScenarioUser):
    abstract = False
    weight = 35
    role_username = "ops@acme.example"
    tasks = [ShopperFlow]


class OpsClerk(ScenarioUser):
    abstract = False
    weight = 20
    role_username = "ops@acme.example"
    tasks = [OpsFlow]


class CatalogManager(ScenarioUser):
    abstract = False
    weight = 15
    role_username = "ops@acme.example"
    tasks = [CatalogFlow]


class PricingAdmin(ScenarioUser):
    abstract = False
    weight = 10
    role_username = ADMIN_USERNAME
    tasks = [PricingFlow]

    def on_start(self) -> None:
        super().on_start()
        self._required(
            "POST",
            f"{API}/fraud/blocklist",
            payload={
                "entries": [
                    {
                        "entry_type": "ip",
                        "value": SUSPICIOUS_IP,
                        "reason": "Scenario fraud screening",
                    }
                ]
            },
            name="/fraud/blocklist",
        )


class Analyst(ScenarioUser):
    abstract = False
    weight = 10
    role_username = "analyst@acme.example"
    tasks = [AnalystFlow]


class Integrator(ScenarioUser):
    abstract = False
    weight = 5
    role_username = "ops@acme.example"
    tasks = [IntegratorFlow]


class HealthProbe(HttpUser):
    abstract = False
    fixed_count = 1
    wait_time = constant(1)

    @task
    def probe_health(self) -> None:
        self.client.get("/health", name="/health")
