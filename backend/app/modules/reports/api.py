"""Report routes (MP11): the catalogue, and each report as JSON (the screen), CSV, XLSX or a printable page.
Read-only, `report.read` (admin, production, owner, auditor)."""

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.reports import domain, service
from app.modules.reports.domain import Report

router = APIRouter(prefix="/api/reports", tags=["reports"])
DbSession = Annotated[Session, Depends(get_session)]
Reader = Annotated[Principal, Depends(require("report.read"))]
Format = Literal["json", "csv", "xlsx", "html"]

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render(report: Report, fmt: Format) -> Any:
    start = report.filters.get("from", report.filters.get("as_of", ""))
    stem = f"{report.name}_{start}_{report.filters.get('to', '')}".rstrip("_")
    if fmt == "csv":
        return Response(
            domain.to_csv(report),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'},
        )
    if fmt == "xlsx":
        return Response(
            domain.to_xlsx(report),
            media_type=XLSX_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'},
        )
    if fmt == "html":
        return HTMLResponse(domain.to_html(report))
    return report.to_json()


@router.get("")
def catalogue(_principal: Reader) -> dict[str, Any]:
    return {"reports": service.catalogue()}


@router.get("/stock-ledger")
def stock_ledger(
    _principal: Reader,
    session: DbSession,
    item_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    format: Format = "json",
) -> Any:
    return render(service.stock_ledger(session, item_id, date_from, date_to), format)


@router.get("/receivables-ageing")
def ageing(_principal: Reader, session: DbSession, as_of: date | None = None, format: Format = "json") -> Any:
    return render(service.receivables_ageing(session, as_of), format)


@router.get("/sales-register")
def sales_register(
    _principal: Reader,
    session: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    format: Format = "json",
) -> Any:
    return render(service.sales_register(session, date_from, date_to, customer_id, item_id), format)


@router.get("/{name}")
def report(
    name: Annotated[str, Query(pattern=r"^[a-z-]{3,40}$")] | str,
    _principal: Reader,
    session: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    format: Format = "json",
) -> Any:
    fn = service.REPORTS.get(name)
    if fn is None or name in ("sales-register", "receivables-ageing"):
        raise service.ReportError("unknown_report", f"no report called {name!r}")
    return render(fn(session, date_from, date_to), format)
