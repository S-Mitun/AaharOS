"""FastAPI entry point. Each module's api.py router is included here as the module is built."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import (
    db_models as _db_models,  # noqa: F401 - registers every table, so ORM flushes can resolve cross-module FKs
)
from app.core.config import get_settings
from app.core.context import CORRELATION_HEADER, CorrelationIdMiddleware
from app.core.errors import NotFoundError, install_error_handlers
from app.modules.audit.api import router as audit_router
from app.modules.billing.api import router as billing_router
from app.modules.collections.api import router as collections_router
from app.modules.costing.api import router as costing_router
from app.modules.dispatch.api import router as dispatch_router
from app.modules.identity.api import auth_router, identity_router
from app.modules.judge.api import router as guide_router
from app.modules.judge.api import signup_router
from app.modules.ledger.api import router as stock_router
from app.modules.planning.api import router as planning_router
from app.modules.procurement.api import router as purchases_router
from app.modules.production.api import router as runs_router
from app.modules.recipe.api import router as recipes_router
from app.modules.reports.api import router as reports_router
from app.modules.sales.api import router as sales_router
from app.modules.tax.api import router as tax_router
from app.modules.traceability.api import public_router as public_trace_router
from app.modules.traceability.api import router as trace_router
from app.modules.valuation.api import router as valuation_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AaharOS API", version="0.1.0", summary="Every gram traced. Every rupee explained.")
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[CORRELATION_HEADER],
    )
    install_error_handlers(app)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.env}

    app.include_router(guide_router)
    app.include_router(auth_router)
    app.include_router(identity_router)
    app.include_router(sales_router)
    app.include_router(audit_router)
    app.include_router(stock_router)
    app.include_router(valuation_router)
    app.include_router(purchases_router)
    app.include_router(recipes_router)
    app.include_router(runs_router)
    app.include_router(costing_router)
    app.include_router(billing_router)
    app.include_router(dispatch_router)
    app.include_router(collections_router)
    app.include_router(tax_router)
    app.include_router(reports_router)
    app.include_router(planning_router)
    app.include_router(trace_router)
    app.include_router(public_trace_router)
    app.include_router(signup_router)
    if settings.web_dist is not None:
        mount_web(app, settings.web_dist)
    return app


def mount_web(app: FastAPI, dist: Path) -> None:
    """Deployment: serve the built web app from the API, so the whole demo is one address. Real files (assets, the
    service worker, the manifest) are served as they are; any other non-API path gets index.html (client routes)."""
    root = dist.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def web(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise NotFoundError("not_found", "no such API route")
        wanted = (root / path).resolve()
        if path and wanted.is_file() and wanted.is_relative_to(root):
            hashed = wanted.parent == root / "assets"  # Vite fingerprints these file names
            return FileResponse(
                wanted, headers={"Cache-Control": "public, max-age=31536000, immutable" if hashed else "no-cache"}
            )
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
