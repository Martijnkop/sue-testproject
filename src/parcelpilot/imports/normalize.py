from __future__ import annotations

from itertools import chain

from parcelpilot.imports import cleaners, repository
from parcelpilot.orders import repo as order_repository


def normalize_job(tenant_id: int, job_id: int) -> dict[str, int]:
    job = repository.get_job(tenant_id, job_id)
    if job is None:
        raise LookupError("import job not found")
    options = job["params"].get("normalization", {})
    batch_size = int(options.get("batch_size", 5000))
    normalized_count = 0
    rows = job["rows"]
    batches = (rows[start:start + batch_size] for start in range(0, len(rows), batch_size))
    for row in chain.from_iterable(batches):
        if row["status"] == "failed":
            continue
        raw = row["raw"]
        if options.get("only_unnormalized", True) and raw.get("_normalized"):
            continue
        if options.get("normalize_prices", True):
            raw["unit_price_cents"] = cleaners.to_cents(str(raw.get("unit_price") or "0"))
        if options.get("normalize_addresses", True):
            raw["ship_line1"] = (raw.get("ship_line1") or "").strip()
            raw["ship_line2"] = (raw.get("ship_line2") or "").strip() or None
            raw["ship_region"] = (raw.get("ship_region") or "").strip() or None
            raw["ship_postal_code"] = cleaners.clean_postal(raw.get("ship_postal_code"))
            raw["ship_city"] = cleaners.title_city(raw.get("ship_city"))
            raw["_geocode"] = cleaners.geocode_stub(raw.get("ship_postal_code"), raw.get("ship_country"))
            raw["ship_country"] = raw["_geocode"]["country"]
        raw["_normalized"] = True
        if row["order_id"] is not None:
            order_repository.update_imported_details(
                tenant_id,
                int(row["order_id"]),
                shipping_address={
                    "line1": raw.get("ship_line1"),
                    "line2": raw.get("ship_line2"),
                    "city": raw.get("ship_city"),
                    "region": raw.get("ship_region"),
                    "postal_code": raw.get("ship_postal_code"),
                    "country_code": raw.get("ship_country"),
                },
                item_prices={
                    str(raw.get("sku") or "").strip().upper(): int(raw["unit_price_cents"])
                } if "unit_price_cents" in raw else {},
            )
        normalized_count += 1
    repository.update_job(tenant_id, job_id, rows=job["rows"], status="completed", finished_at=repository.datetime_now())
    return {"normalized_rows": normalized_count}
