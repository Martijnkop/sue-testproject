from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
import threading
from typing import Any

import bcrypt
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from parcelpilot.db.base import Base
from parcelpilot.db.models import UserRole
from parcelpilot.db.session import engine
from parcelpilot.dev.seeder import ordered_domains, run_workload_seed, tenant_has_workload
from parcelpilot.dev.workloads import WORKLOADS, validate_workloads
from parcelpilot.settings import settings

router = APIRouter(prefix="/_seed", tags=["seed"])
logger = logging.getLogger(__name__)

_DEFAULT_USERS: list[dict[str, str]] = [
    {"email": "admin@acme.example", "full_name": "Acme Admin", "role": "admin"},
    {"email": "ops@acme.example", "full_name": "Acme Ops", "role": "ops"},
    {"email": "analyst@acme.example", "full_name": "Acme Analyst", "role": "analyst"},
    {"email": "viewer@acme.example", "full_name": "Acme Viewer", "role": "viewer"},
]

_SEED_STATE: dict[str, Any] = {
    "workload": None,
    "scale": None,
    "seeded_at": None,
    "seeded_tenants": set(),
    "tenant_id": None,
}

_SEED_JOBS: dict[int, dict[str, Any]] = {}
_SEED_LOCK = threading.Lock()
_SEEDING_TENANTS: set[str] = set()


class SeedResetRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confirm: bool = False


class SeedTenantUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str
    full_name: str
    role: str = "viewer"
    password: str | None = None


class SeedTenantRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    slug: str = "acme"
    name: str = "Acme"
    users: list[SeedTenantUser] = Field(default_factory=list)


class SeedWorkloadRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tenant_slug: str = "acme"
    scale: float | None = None
    rng_seed: int | None = None
    domains: list[str] | None = None


class SeedImportRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    workload: str = "benign"
    rows: int = 100
    bad_row_pct: int = 0
    format: str = "csv"


def _seed_guard(x_seed_key: str | None = Header(default=None, alias="X-Seed-Key")) -> str:
    if not settings.seed_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "seed_disabled", "message": "Seed endpoints are disabled"},
        )
    if x_seed_key is None or x_seed_key != settings.seed_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_seed_key", "message": "Invalid or missing X-Seed-Key header"},
        )
    return x_seed_key


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode("utf-8")


def _user_rows_for_tenant(request: SeedTenantRequest) -> list[dict[str, str]]:
    users = request.users or [SeedTenantUser(**payload) for payload in _DEFAULT_USERS]
    for user in users:
        if user.password is None:
            user.password = "Password123!"
    return [
        {"email": user.email, "full_name": user.full_name, "role": user.role, "password": user.password}
        for user in users
    ]


def _make_seed_job(workload_name: str, tenant_slug: str, domains: list[str]) -> dict[str, Any]:
    job_id = max(_SEED_JOBS.keys(), default=0) + 1
    payload = {
        "job_id": job_id,
        "workload": workload_name,
        "tenant_slug": tenant_slug,
        "status": "queued",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "progress": {domain: 0 for domain in domains},
        "domains": domains,
    }
    _SEED_JOBS[job_id] = payload
    return payload


def _complete_seed_job(job_id: int) -> dict[str, Any]:
    job = _SEED_JOBS[job_id]
    job["status"] = "completed"
    job["updated_at"] = _utc_now()
    job["progress"] = {domain: 100 for domain in job["domains"]}
    return job


def _run_seed_job(
    job_id: int,
    workload_name: str,
    tenant_slug: str,
    scale: float,
    rng_seed: int,
    domains: list[str] | None,
) -> None:
    job = _SEED_JOBS[job_id]
    job["status"] = "running"
    job["updated_at"] = _utc_now()

    def update_progress(domain: str, percentage: int) -> None:
        if domain not in job["progress"]:
            job["domains"].append(domain)
            job["progress"][domain] = 0
        job["progress"][domain] = percentage
        job["updated_at"] = _utc_now()

    try:
        with engine.begin() as connection:
            tenant_id = run_workload_seed(
                connection=connection,
                workload=workload_name,
                tenant_slug=tenant_slug,
                scale=scale,
                rng_seed=rng_seed,
                config=validate_workloads(WORKLOADS)[workload_name],
                domains=domains,
                progress=update_progress,
            )

        _SEED_STATE["workload"] = workload_name
        _SEED_STATE["scale"] = scale
        _SEED_STATE["seeded_at"] = _utc_now()
        _SEED_STATE["tenant_id"] = tenant_id
        _SEED_STATE["seeded_tenants"].add(tenant_slug)
        _complete_seed_job(job_id)
    except Exception as error:
        job["status"] = "failed"
        job["error"] = str(error)
        job["updated_at"] = _utc_now()
        logger.exception("Workload seed job %s failed", job_id)
        raise
    finally:
        _SEEDING_TENANTS.discard(tenant_slug)


def _generate_samples(kind: str, count: int) -> list[str | int]:
    from parcelpilot.catalog.api import _PRODUCTS
    from parcelpilot.customers.api import _CUSTOMERS
    from parcelpilot.warehouses.api import _WAREHOUSES

    if kind == "customer_ids":
        return sorted(int(customer["id"]) for customer in _CUSTOMERS.values())[:count]
    if kind == "warehouse_ids":
        return sorted(_WAREHOUSES)[:count]
    if kind == "order_ids":
        from parcelpilot.orders import repo as order_repository

        tenant_id = int(_SEED_STATE.get("tenant_id") or 1)
        return sorted(int(order["id"]) for order in order_repository.list_for_tenant(tenant_id))[:count]
    if kind == "product_skus":
        return sorted(_PRODUCTS)[:count]
    if kind == "emails":
        return sorted(str(customer["email"]) for customer in _CUSTOMERS.values())[:count]
    if kind in {"shipment_ids", "tracking_numbers"}:
        return []
    if kind == "tenant_slugs":
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT slug FROM tenants ORDER BY id LIMIT :count"),
                {"count": count},
            ).scalars()
            return list(rows)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "unsupported_sample_kind", "message": f"Unsupported sample kind '{kind}'"},
    )


def _import_file_content(workload_name: str, row_count: int, bad_row_pct: int, file_format: str) -> tuple[str, str]:
    file_format = file_format.lower()
    if file_format not in {"csv", "ndjson"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "unsupported_format", "message": "Format must be csv or ndjson"},
        )
    if not 0 <= bad_row_pct <= 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_bad_row_pct", "message": "bad_row_pct must be between 0 and 100"},
        )

    bad_rows = int((row_count * bad_row_pct) / 100)
    rows: list[dict[str, str]] = []
    for index in range(row_count):
        rows.append({
            "external_ref": f"ext-{workload_name}-{index:08d}",
            "customer_email": f"customer{index}@example.com",
            "sku": f"ACM-{index % 1000 + 1:06d}",
            "quantity": "not-a-number" if index < bad_rows else str(index % 5 + 1),
            "unit_price": f"{12 + index % 100}.50",
            "currency": "EUR",
            "ship_line1": "Karl-Heine-Str. 12",
            "ship_line2": "",
            "ship_city": "leipzig",
            "ship_region": "",
            "ship_postal_code": " 04229 ",
            "ship_country": "DE",
            "placed_at": "2026-10-10T08:00:00Z",
        })

    if file_format == "csv":
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(rows[0]) if rows else [
            "external_ref", "customer_email", "sku", "quantity", "unit_price", "currency",
            "ship_line1", "ship_line2", "ship_city", "ship_region", "ship_postal_code",
            "ship_country", "placed_at",
        ])
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue(), "text/csv"

    body = "\n".join(json.dumps(row) for row in rows)
    return body, "application/x-ndjson"


@router.post("/reset")
def reset_seed_state(payload: SeedResetRequest, x_seed_key: str | None = Header(default=None, alias="X-Seed-Key")) -> dict[str, Any]:
    _seed_guard(x_seed_key)
    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "confirmation_required", "message": "Reset requires confirm=true"},
        )
    with _SEED_LOCK:
        if _SEEDING_TENANTS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "seed_in_progress", "message": "Cannot reset while a workload seed is running"},
            )

        with engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))

        _SEED_STATE["seeded_at"] = _utc_now()
        _SEED_STATE["workload"] = None
        _SEED_STATE["scale"] = None
        _SEED_STATE["seeded_tenants"] = set()
        _SEED_STATE["tenant_id"] = None
        _SEED_JOBS.clear()

    return {"status": "ok", "message": "Database reset completed", "seeded_at": _SEED_STATE["seeded_at"]}


@router.post("/tenants")
def create_tenant(payload: SeedTenantRequest, x_seed_key: str | None = Header(default=None, alias="X-Seed-Key")) -> dict[str, Any]:
    _seed_guard(x_seed_key)

    tenant_slug = payload.slug or "acme"
    tenant_name = payload.name or "Acme"

    with engine.begin() as connection:
        existing_tenant = connection.execute(
            text("SELECT 1 FROM tenants WHERE slug = :slug LIMIT 1"),
            {"slug": tenant_slug},
        ).first()
        if existing_tenant:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "tenant_exists", "message": f"Tenant with slug '{tenant_slug}' already exists"},
            )

        tenant_result = connection.execute(
            text(
                "INSERT INTO tenants (name, slug, plan, is_active, created_at) VALUES (:name, :slug, :plan, :is_active, NOW()) RETURNING id"
            ),
            {"name": tenant_name, "slug": tenant_slug, "plan": "standard", "is_active": True},
        )
        tenant_id = tenant_result.scalar_one()

        created_users: list[dict[str, str]] = []
        for user in _user_rows_for_tenant(payload):
            role = user["role"]
            if role not in {member.value for member in UserRole}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "invalid_role", "message": f"Unsupported role '{role}'"},
                )
            user_password = user["password"]
            user_hash = _hash_password(user_password)
            user_result = connection.execute(
                text(
                    "INSERT INTO users (tenant_id, email, full_name, password_hash, role, is_active, created_at) VALUES (:tenant_id, :email, :full_name, :password_hash, :role, :is_active, NOW()) RETURNING id"
                ),
                {
                    "tenant_id": tenant_id,
                    "email": user["email"],
                    "full_name": user["full_name"],
                    "password_hash": user_hash,
                    "role": role,
                    "is_active": True,
                },
            )
            created_users.append(
                {
                    "id": str(user_result.scalar_one()),
                    "email": user["email"],
                    "full_name": user["full_name"],
                    "role": role,
                    "password": user_password,
                }
            )

    _SEED_STATE["seeded_at"] = _utc_now()
    _SEED_STATE["workload"] = "manual"
    _SEED_STATE["scale"] = 1.0
    _SEED_STATE["tenant_id"] = int(tenant_id)

    return {
        "status": "ok",
        "tenant": {"id": tenant_id, "slug": tenant_slug, "name": tenant_name},
        "users": created_users,
        "seeded_at": _SEED_STATE["seeded_at"],
    }


@router.get("/status")
def seed_status(x_seed_key: str | None = Header(default=None, alias="X-Seed-Key")) -> dict[str, Any]:
    _seed_guard(x_seed_key)

    row_counts: dict[str, int] = {}
    with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            count = connection.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar_one()
            row_counts[table.name] = int(count)

        tenants = connection.execute(text("SELECT id, slug, name FROM tenants ORDER BY id")).fetchall()

    return {
        "row_counts": row_counts,
        "workload": _SEED_STATE["workload"],
        "scale": _SEED_STATE["scale"],
        "seeded_at": _SEED_STATE["seeded_at"],
        "tenants": [{"id": tenant[0], "slug": tenant[1], "name": tenant[2]} for tenant in tenants],
    }


@router.post("/workloads/{workload}")
def seed_workload(
    workload: str,
    payload: SeedWorkloadRequest,
    background_tasks: BackgroundTasks,
    x_seed_key: str | None = Header(default=None, alias="X-Seed-Key"),
) -> JSONResponse:
    _seed_guard(x_seed_key)
    workload_name = workload.lower()
    if workload_name not in WORKLOADS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "unknown_workload", "message": f"Unknown workload '{workload}'"},
        )
    tenant_slug = payload.tenant_slug or "acme"
    config = validate_workloads(WORKLOADS)[workload_name]
    resolved_scale = float(config["scale"] if payload.scale is None else payload.scale)
    if not 0.01 <= resolved_scale <= 1.0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_scale", "message": "Scale must be between 0.01 and 1.0"},
        )
    resolved_rng_seed = int(config["rng_seed"] if payload.rng_seed is None else payload.rng_seed)
    requested_domains = payload.domains or [
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
    try:
        chosen_domains = ordered_domains(requested_domains)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_domains", "message": str(error)},
        ) from error

    with _SEED_LOCK:
        if tenant_slug in _SEED_STATE["seeded_tenants"] or tenant_slug in _SEEDING_TENANTS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "tenant_already_seeded", "message": f"Tenant '{tenant_slug}' has already been seeded"},
            )
        with engine.connect() as connection:
            tenant_id = connection.execute(
                text("SELECT id FROM tenants WHERE slug = :slug"),
                {"slug": tenant_slug},
            ).scalar_one_or_none()
            if tenant_id is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "tenant_not_found", "message": f"Tenant '{tenant_slug}' does not exist"},
                )
            if tenant_has_workload(connection, int(tenant_id)):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "tenant_already_seeded", "message": f"Tenant '{tenant_slug}' has already been seeded"},
                )

        job = _make_seed_job(workload_name, tenant_slug, chosen_domains)
        job["scale"] = resolved_scale
        job["rng_seed"] = resolved_rng_seed
        _SEEDING_TENANTS.add(tenant_slug)

    background_tasks.add_task(
        _run_seed_job,
        job["job_id"],
        workload_name,
        tenant_slug,
        resolved_scale,
        resolved_rng_seed,
        chosen_domains,
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "job_id": job["job_id"],
            "job_type": "seed",
            "status": "queued",
            "status_url": f"/api/v1/_seed/jobs/{job['job_id']}",
        },
    )


@router.get("/jobs/{job_id}")
def get_seed_job(job_id: int, x_seed_key: str | None = Header(default=None, alias="X-Seed-Key")) -> dict[str, Any]:
    _seed_guard(x_seed_key)
    job = _SEED_JOBS.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "job_not_found", "message": f"Seed job '{job_id}' does not exist"},
        )
    return {
        "job_id": job["job_id"],
        "workload": job["workload"],
        "tenant_slug": job["tenant_slug"],
        "status": job["status"],
        "progress": job["progress"],
        "domains": job["domains"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "error": job.get("error"),
    }


@router.get("/samples")
def get_seed_samples(
    kind: str = Query(default="customer_ids"),
    n: int = Query(default=10, ge=1, le=500),
    x_seed_key: str | None = Header(default=None, alias="X-Seed-Key"),
) -> dict[str, Any]:
    _seed_guard(x_seed_key)
    return {"kind": kind, "count": n, "items": _generate_samples(kind, n)}


@router.get("/import-file")
def generate_seed_import_file(
    workload: str = Query(default="benign"),
    rows: int = Query(default=100, ge=1, le=100000),
    bad_row_pct: int = Query(default=0, ge=0, le=100),
    format: str = Query(default="csv"),
    x_seed_key: str | None = Header(default=None, alias="X-Seed-Key"),
) -> Response:
    _seed_guard(x_seed_key)
    workload_name = workload.lower()
    if workload_name not in WORKLOADS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "unknown_workload", "message": f"Unknown workload '{workload}'"},
        )
    content, media_type = _import_file_content(workload_name, rows, bad_row_pct, format)
    filename = f"seed_{workload_name}.{format.lower()}"
    return PlainTextResponse(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
