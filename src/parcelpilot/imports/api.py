from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from parcelpilot.core.security import get_current_user, require_roles
from parcelpilot.customers.api import _CUSTOMERS
from parcelpilot.imports import cleaners, normalize, repository
from parcelpilot.orders import service as order_service
from parcelpilot.orders import repo as order_repository
from parcelpilot.orders.schemas import OrderCreate

router = APIRouter(prefix="/imports", tags=["imports"])
MAX_FILE_BYTES = 500 * 1024 * 1024
_REQUIRED_COLUMNS = {
    "external_ref", "customer_email", "sku", "quantity", "unit_price", "currency",
    "ship_line1", "ship_line2", "ship_city", "ship_region", "ship_postal_code",
    "ship_country", "placed_at",
}


@router.get("")
def imports_root() -> dict[str, str]:
    return {"status": "ok"}


class NormalizeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    normalize_addresses: bool = True
    normalize_prices: bool = True
    only_unnormalized: bool = True
    batch_size: int = Field(default=5000, ge=1, le=20000)


def _stage_upload(file: UploadFile, file_format: str) -> list[dict[str, Any]]:
    file.file.seek(0, 2)
    size = file.file.tell()
    if size > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail={"code": "file_too_large", "message": "Import files must not exceed 500 MB"})
    file.file.seek(0)
    text_stream = io.TextIOWrapper(file.file, encoding="utf-8-sig", newline="")
    if file_format == "csv":
        try:
            reader = csv.DictReader(text_stream)
            if reader.fieldnames is None or not _REQUIRED_COLUMNS.issubset(reader.fieldnames):
                raise HTTPException(status_code=422, detail={"code": "invalid_import_columns", "message": "CSV is missing required order columns"})
            return [dict(row) for row in reader]
        except (UnicodeDecodeError, csv.Error) as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_import_file", "message": "CSV file encoding or structure is invalid"}) from exc
        finally:
            text_stream.detach()
    try:
        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(text_stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                rows.append({"_parse_error": f"invalid NDJSON on line {line_number}: {exc.msg}"})
                continue
            if not isinstance(row, dict):
                rows.append({"_parse_error": f"NDJSON line {line_number} must be an object"})
            else:
                rows.append(row)
        return rows
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_import_file", "message": "NDJSON must be UTF-8 encoded"}) from exc
    finally:
        text_stream.detach()


def _process_job(tenant_id: int, job_id: int) -> None:
    job = repository.get_job(tenant_id, job_id)
    if job is None:
        raise LookupError(f"Import job {job_id} was not found")
    rows = job["rows"]
    repository.update_job(tenant_id, job_id, status="running", started_at=datetime.now(timezone.utc))
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        raw = row["raw"]
        if row.get("error"):
            continue
        external_ref = str(raw.get("external_ref") or "").strip()
        if not external_ref:
            row.update(status="failed", error="external_ref is required")
            continue
        groups.setdefault(external_ref, []).append(row)

    customers_by_email = {str(customer.get("email", "")).casefold(): customer for customer in _CUSTOMERS.values()}
    created = 0
    for external_ref, group in groups.items():
        first = group[0]["raw"]
        customer = customers_by_email.get(str(first.get("customer_email", "")).strip().casefold())
        if customer is None:
            for row in group:
                row.update(status="failed", error="unknown customer_email")
            continue
        try:
            consistent_fields = (
                "customer_email", "currency", "ship_line1", "ship_line2", "ship_city",
                "ship_region", "ship_postal_code", "ship_country", "placed_at",
            )
            if any(any(row["raw"].get(field) != first.get(field) for field in consistent_fields) for row in group[1:]):
                raise ValueError("order lines sharing external_ref must have matching order details")
            address = {
                "line1": str(first.get("ship_line1") or ""),
                "line2": first.get("ship_line2") or None,
                "city": str(first.get("ship_city") or ""),
                "region": first.get("ship_region") or None,
                "postal_code": str(first.get("ship_postal_code") or ""),
                "country_code": str(first.get("ship_country") or "DE"),
            }
            unit_prices = {
                str(row["raw"].get("sku") or "").strip().upper(): cleaners.to_cents(str(row["raw"].get("unit_price") or "0"))
                for row in group
            }
            if any(price < 0 for price in unit_prices.values()):
                raise ValueError("unit_price must not be negative")
            placed_text = str(first.get("placed_at") or "").strip()
            placed_at = datetime.fromisoformat(placed_text.replace("Z", "+00:00")) if placed_text else datetime.now(timezone.utc)
            if placed_at.tzinfo is None:
                placed_at = placed_at.replace(tzinfo=timezone.utc)
            order_payload = {
                "customer_id": int(customer["id"]),
                "external_ref": external_ref,
                "currency": str(first.get("currency") or job["params"]["default_currency"]).upper(),
                "items": [
                    {"sku": str(row["raw"].get("sku") or ""), "quantity": int(row["raw"].get("quantity") or 0)}
                    for row in group
                ],
                "shipping_address": address,
            }
            OrderCreate.model_validate(order_payload)
            order = None if job["dry_run"] else order_service.create_order(
                json.dumps(order_payload), tenant_id, source="bulk_import",
                unit_price_overrides=unit_prices, placed_at=placed_at,
            )
            order_id = int(order["id"]) if order is not None else None
            for row in group:
                row["raw"]["unit_price_cents"] = unit_prices[str(row["raw"].get("sku") or "").strip().upper()]
                row.update(status="imported", error=None, order_id=order_id)
            if order is not None:
                created += 1
        except (ValueError, TypeError, KeyError, HTTPException) as exc:
            message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
            for row in group:
                row.update(status="failed", error=message)

    failed = sum(row["status"] == "failed" for row in rows)
    repository.update_job(
        tenant_id, job_id, rows=rows, status="completed", processed_rows=len(rows) - failed,
        failed_rows=failed, orders_created=created, finished_at=datetime.now(timezone.utc),
        error_summary=f"{failed} row(s) failed" if failed else None,
    )


@router.post("/orders", status_code=status.HTTP_202_ACCEPTED)
async def upload_orders(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    format: str = Form(default="csv"),
    dry_run: bool = Form(default=False),
    default_currency: str = Form(default="EUR"),
    batch_size: int = Form(default=1000, ge=1, le=20000),
    user: dict[str, Any] = Depends(require_roles("admin", "ops")),
) -> dict[str, Any]:
    file_format = format.lower()
    if file_format not in {"csv", "ndjson"}:
        raise HTTPException(status_code=422, detail={"code": "unsupported_format", "message": "format must be csv or ndjson"})
    if len(default_currency) != 3 or not default_currency.isalpha():
        raise HTTPException(status_code=422, detail={"code": "invalid_currency", "message": "default_currency must be a three-letter code"})
    rows = _stage_upload(file, file_format)
    tenant_id = int(user["tenant_id"])
    job = repository.create_job(
        tenant_id, int(user["user_id"]), file.filename or "upload", file_format, dry_run,
        {"default_currency": default_currency.upper(), "batch_size": batch_size},
    )
    for start in range(0, len(rows), batch_size):
        staged = [
            {"row_number": index + 1, "raw": rows[index], "status": "failed" if "_parse_error" in rows[index] else "pending",
             "error": rows[index].get("_parse_error"), "order_id": None}
            for index in range(start, min(start + batch_size, len(rows)))
        ]
        repository.append_rows(tenant_id, job["id"], staged)
    background_tasks.add_task(_process_job, tenant_id, job["id"])
    return {"job_id": job["id"], "job_type": "import", "status": "queued"}


@router.get("/{job_id}")
def get_import_job(job_id: int, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    job = repository.get_job(int(user["tenant_id"]), job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "import_not_found", "message": "Import job not found"})
    return {key: job[key] for key in (
        "id", "status", "source_filename", "format", "dry_run", "total_rows", "processed_rows",
        "failed_rows", "orders_created", "started_at", "finished_at", "error_summary",
    )}


@router.get("/{job_id}/rows")
def get_import_rows(
    job_id: int,
    status_filter: str | None = Query(default=None, alias="status", pattern="^(pending|imported|failed|skipped)$"),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    tenant_id = int(user["tenant_id"])
    if repository.get_job(tenant_id, job_id) is None:
        raise HTTPException(status_code=404, detail={"code": "import_not_found", "message": "Import job not found"})
    items, total = repository.list_rows(tenant_id, job_id, status_filter, offset, limit)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/{job_id}/normalize", status_code=status.HTTP_202_ACCEPTED)
def normalize_import(
    job_id: int,
    payload: NormalizeRequest,
    background_tasks: BackgroundTasks,
    user: dict[str, Any] = Depends(require_roles("admin", "ops")),
) -> dict[str, Any]:
    tenant_id = int(user["tenant_id"])
    job = repository.get_job(tenant_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "import_not_found", "message": "Import job not found"})
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail={"code": "import_not_complete", "message": "Only completed imports can be normalized"})
    options = payload.model_dump()
    repository.update_job(tenant_id, job_id, status="normalizing", params={**job["params"], "normalization": options})
    background_tasks.add_task(normalize.normalize_job, tenant_id, job_id)
    return {"job_id": job_id, "job_type": "import", "status": "normalizing"}
