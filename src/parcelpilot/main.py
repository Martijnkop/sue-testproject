from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI
from sqlalchemy import text

from parcelpilot.analytics.api import router as analytics_router
from parcelpilot.auth.api import router as auth_router
from parcelpilot.catalog.api import router as catalog_router
from parcelpilot.core.errors import register_exception_handlers
from parcelpilot.core.logging import configure_logging
from parcelpilot.core.middleware import RequestIDMiddleware
from parcelpilot.customers.api import router as customers_router
from parcelpilot.db.session import SessionLocal
from parcelpilot.dev.api import router as seed_router
from parcelpilot.exports.api import router as exports_router
from parcelpilot.fraud.api import router as fraud_router
from parcelpilot.imports.api import router as imports_router
from parcelpilot.metrics.api import router as metrics_router
from parcelpilot.orders.api import router as orders_router
from parcelpilot.pricing.api import router as pricing_router
from parcelpilot.reports.api import router as reports_router
from parcelpilot.routing.api import router as routing_router
from parcelpilot.scoring.api import router as scoring_router
from parcelpilot.shipments.api import router as shipments_router
from parcelpilot.slotting.api import router as slotting_router
from parcelpilot.warehouses.api import router as warehouses_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(title="ParcelPilot", version="0.1.0")
    app.state.started_at = time.monotonic()
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)

    app.include_router(seed_router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(customers_router, prefix=API_PREFIX)
    app.include_router(warehouses_router, prefix=API_PREFIX)
    app.include_router(catalog_router, prefix=API_PREFIX)
    app.include_router(pricing_router, prefix=API_PREFIX)
    app.include_router(fraud_router, prefix=API_PREFIX)
    app.include_router(orders_router, prefix=API_PREFIX)
    app.include_router(imports_router, prefix=API_PREFIX)
    app.include_router(reports_router, prefix=API_PREFIX)
    app.include_router(analytics_router, prefix=API_PREFIX)
    app.include_router(routing_router, prefix=API_PREFIX)
    app.include_router(slotting_router, prefix=API_PREFIX)
    app.include_router(scoring_router, prefix=API_PREFIX)
    app.include_router(metrics_router, prefix=API_PREFIX)
    app.include_router(shipments_router, prefix=API_PREFIX)
    app.include_router(exports_router, prefix=API_PREFIX)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        uptime_seconds = int(time.monotonic() - app.state.started_at)
        db_status = "ok"

        try:
            with SessionLocal() as session:
                session.execute(text("SELECT 1"))
        except Exception:
            db_status = "error"

        return {"status": "ok", "version": app.version, "uptime_s": uptime_seconds, "db": db_status}

    return app


app = create_app()
