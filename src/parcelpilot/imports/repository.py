from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

_JOBS: dict[tuple[int, int], dict[str, Any]] = {}
_SEQUENCE = 0


def datetime_now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(tenant_id: int, user_id: int, filename: str, file_format: str, dry_run: bool, params: dict[str, Any]) -> dict[str, Any]:
    global _SEQUENCE
    _SEQUENCE += 1
    job = {
        "id": _SEQUENCE,
        "tenant_id": tenant_id,
        "created_by": user_id,
        "source_filename": filename[:255],
        "format": file_format,
        "status": "queued",
        "dry_run": dry_run,
        "params": copy.deepcopy(params),
        "rows": [],
        "total_rows": 0,
        "processed_rows": 0,
        "failed_rows": 0,
        "orders_created": 0,
        "started_at": None,
        "finished_at": None,
        "error_summary": None,
        "created_at": datetime_now(),
    }
    _JOBS[(tenant_id, _SEQUENCE)] = job
    return copy.deepcopy(job)


def get_job(tenant_id: int, job_id: int) -> dict[str, Any] | None:
    job = _JOBS.get((tenant_id, job_id))
    return copy.deepcopy(job) if job is not None else None


def update_job(tenant_id: int, job_id: int, **fields: Any) -> None:
    job = _JOBS.get((tenant_id, job_id))
    if job is not None:
        job.update(fields)


def append_rows(tenant_id: int, job_id: int, rows: list[dict[str, Any]]) -> None:
    job = _JOBS[(tenant_id, job_id)]
    job["rows"].extend(copy.deepcopy(rows))
    job["total_rows"] = len(job["rows"])


def list_rows(tenant_id: int, job_id: int, status: str | None, offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
    job = _JOBS.get((tenant_id, job_id))
    if job is None:
        return [], 0
    rows = job["rows"]
    if status is not None:
        rows = [row for row in rows if row["status"] == status]
    return copy.deepcopy(rows[offset:offset + limit]), len(rows)
